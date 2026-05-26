import json
import httpx
import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID
from typing import Dict, List, Any

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models.academic import ClassEnrollment, Class, Course
from app.models.session_attendance import ClassSession
from app.models.test import TestAttempt, TestResponse, QuestionBank, AttemptStatus, Test, SkillArea, DifficultyLevel, ContentStatus, TestQuestion
from app.models.user import User
from app.models.recommendation import RecommendationLog
from app.core.config import settings
from app.core.redis import redis_manager
from app.core.exceptions import APIException

logger = logging.getLogger(__name__)


class RecommendationService:
    """
    Production recommendation service — no mock fallback.
    Calls tungtung-recommendation AI service for real ML inference + LLM generation.
    """

    # ─── Data Aggregation Queries ─────────────────────────────────────

    def get_student_skill_scores(self, db: Session, student_id: UUID) -> Dict[str, float]:
        """
        Query 3 bài test gần nhất PER SKILL, tính trung bình.
        """
        # Fetch all graded attempts for the student
        attempts = db.query(TestAttempt.id)\
            .filter(
                TestAttempt.student_id == student_id,
                TestAttempt.status == AttemptStatus.GRADED
            )\
            .order_by(desc(TestAttempt.submitted_at))\
            .all()
            
        attempt_ids = [a[0] for a in attempts]
        if not attempt_ids:
            return {}

        # Fetch responses for these attempts, join with QuestionBank to get skill_area
        responses = db.query(
            QuestionBank.skill_area,
            TestAttempt.submitted_at,
            TestResponse.teacher_band_score,
            TestResponse.ai_band_score,
            TestResponse.band_score,
            TestResponse.points_earned
        ).select_from(TestResponse)\
         .join(TestAttempt, TestAttempt.id == TestResponse.attempt_id)\
         .join(QuestionBank, QuestionBank.id == TestResponse.question_id)\
         .filter(TestAttempt.id.in_(attempt_ids))\
         .order_by(desc(TestAttempt.submitted_at))\
         .all()

        skill_history = {}
        for r in responses:
            skill = r.skill_area.value if hasattr(r.skill_area, 'value') else str(r.skill_area)
            # determine score: priority teacher > ai > band > points
            score = r.teacher_band_score
            if score is None:
                score = r.ai_band_score
            if score is None:
                score = r.band_score
            if score is None:
                score = r.points_earned
            
            if score is None:
                continue
                
            if skill not in skill_history:
                skill_history[skill] = []
            
            # We only want top 3 recent scores per skill
            if len(skill_history[skill]) < 3:
                skill_history[skill].append(float(score))

        result = {}
        for skill, scores in skill_history.items():
            if scores:
                result[skill] = round(sum(scores) / len(scores), 2)
        return result

    def get_student_enrollment_data(self, db: Session, student_id: UUID) -> Dict[str, Any]:
        """
        Query enrollment info: attendance_rate, days_enrolled, course_level, start_date
        """
        enrollment = db.query(
            ClassEnrollment.attendance_rate,
            ClassEnrollment.enrollment_date,
            Class.start_date,
            Course.level
        ).select_from(ClassEnrollment)\
         .join(Class, Class.id == ClassEnrollment.class_id)\
         .join(Course, Course.id == Class.course_id)\
         .filter(ClassEnrollment.student_id == student_id)\
         .order_by(desc(ClassEnrollment.enrollment_date))\
         .first()

        if not enrollment:
            return {}

        days_enrolled = 0
        if enrollment.enrollment_date:
            now = datetime.now(enrollment.enrollment_date.tzinfo) if enrollment.enrollment_date.tzinfo else datetime.now(timezone.utc)
            days_enrolled = (now - enrollment.enrollment_date).days

        course_level_str = enrollment.level.value if hasattr(enrollment.level, 'value') else str(enrollment.level)

        return {
            "attendance_rate": float(enrollment.attendance_rate) if enrollment.attendance_rate else 0.0,
            "days_enrolled": days_enrolled,
            "course_level": course_level_str,
            "start_date": enrollment.start_date.isoformat() if enrollment.start_date else None
        }

    def get_student_target(self, db: Session, student_id: UUID) -> Dict[str, Any]:
        """
        Lấy target_band từ users.preferences JSONB
        """
        user = db.query(User).filter(User.id == student_id).first()
        if not user or not user.preferences:
            return {}
        
        prefs = user.preferences
        return {
            "target_band": prefs.get("target_band"),
            "target_cefr": prefs.get("target_cefr")
        }

    def get_days_since_last_activity(self, db: Session, student_id: UUID) -> int:
        """
        Tính số ngày kể từ lần cuối student có hoạt động: test hoặc attendance
        """
        last_test = db.query(func.max(TestAttempt.submitted_at))\
            .filter(TestAttempt.student_id == student_id)\
            .scalar()

        # get last session attendance
        from app.models.session_attendance import AttendanceRecord
        last_attendance = db.query(func.max(AttendanceRecord.check_in_time))\
            .filter(AttendanceRecord.student_id == student_id)\
            .scalar()
            
        times = []
        if last_test:
            times.append(last_test)
        if last_attendance:
            times.append(last_attendance)
            
        if not times:
            return -1  # never active
            
        last_activity = max(times)
        now = datetime.now(last_activity.tzinfo) if last_activity.tzinfo else datetime.now(timezone.utc)
        return (now - last_activity).days

    def get_score_history(self, db: Session, student_id: UUID) -> List[Dict[str, Any]]:
        """
        Lấy lịch sử điểm (tất cả attempts, per skill): [{date, skill, score}]
        """
        responses = db.query(
            QuestionBank.skill_area,
            TestAttempt.submitted_at,
            TestResponse.teacher_band_score,
            TestResponse.ai_band_score,
            TestResponse.band_score,
            TestResponse.points_earned
        ).select_from(TestResponse)\
         .join(TestAttempt, TestAttempt.id == TestResponse.attempt_id)\
         .join(QuestionBank, QuestionBank.id == TestResponse.question_id)\
         .filter(
            TestAttempt.student_id == student_id,
            TestAttempt.status == AttemptStatus.GRADED,
            TestAttempt.submitted_at != None
         )\
         .order_by(TestAttempt.submitted_at)\
         .all()

        history = []
        for r in responses:
            skill = r.skill_area.value if hasattr(r.skill_area, 'value') else str(r.skill_area)
            score = r.teacher_band_score or r.ai_band_score or r.band_score or r.points_earned
            if score is None:
                continue
            history.append({
                "date": r.submitted_at.isoformat(),
                "skill": skill,
                "score": float(score)
            })
        return history

    def get_recent_ai_feedback(self, db: Session, student_id: UUID, limit: int = 5) -> List[str]:
        """
        Query recent AI feedback from graded test responses.
        Returns list of feedback strings for LLM context.
        """
        feedbacks = db.query(TestResponse.ai_feedback)\
            .join(TestAttempt, TestAttempt.id == TestResponse.attempt_id)\
            .filter(
                TestAttempt.student_id == student_id,
                TestAttempt.status == AttemptStatus.GRADED,
                TestResponse.ai_feedback != None,
                TestResponse.ai_feedback != ''
            )\
            .order_by(desc(TestAttempt.submitted_at))\
            .limit(limit)\
            .all()
        
        return [f[0] for f in feedbacks if f[0]]

    def get_suggested_test_ids(self, db: Session, student_id: UUID, weakest_skill: str, difficulty: str = "medium") -> List[str]:
        """
        Query tests matching the student's weakest skill and difficulty level.
        Excludes tests already attempted by the student.
        Returns list of test ID strings.
        """
        # Map skill string to SkillArea enum
        skill_map = {
            "reading": SkillArea.READING,
            "listening": SkillArea.LISTENING,
            "writing": SkillArea.WRITING,
            "speaking": SkillArea.SPEAKING
        }
        skill_enum = skill_map.get(weakest_skill)
        if not skill_enum:
            return []
        
        # Map difficulty string to DifficultyLevel enum
        diff_map = {
            "easy": [DifficultyLevel.VERY_EASY, DifficultyLevel.EASY],
            "medium": [DifficultyLevel.EASY, DifficultyLevel.MEDIUM],
            "hard": [DifficultyLevel.MEDIUM, DifficultyLevel.HARD, DifficultyLevel.VERY_HARD]
        }
        diff_levels = diff_map.get(difficulty, [DifficultyLevel.MEDIUM])
        
        # Get test IDs that the student has already attempted
        attempted_test_ids = db.query(TestAttempt.test_id)\
            .filter(TestAttempt.student_id == student_id)\
            .subquery()
        
        # Find tests that contain questions with the matching skill_area
        # and haven't been attempted by this student
        from sqlalchemy.orm import aliased
        from app.models.test import TestSection
        
        test_ids = db.query(Test.id)\
            .join(TestSection, TestSection.test_id == Test.id)\
            .filter(
                TestSection.skill_area == skill_enum,
                Test.status.in_(['published', 'active']),
                ~Test.id.in_(attempted_test_ids)
            )\
            .distinct()\
            .limit(5)\
            .all()
        
        return [str(t[0]) for t in test_ids]

    # ─── AI Service Call (Production — No Mock) ───────────────────────

    async def call_ai_service(self, student_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Proxy call to tungtung-recommendation AI service.
        No mock fallback — RECOMMENDATION_SERVICE_URL must be configured.
        """
        service_url = getattr(settings, 'RECOMMENDATION_SERVICE_URL', None)
        if not service_url:
            raise APIException(
                status_code=503,
                code="AI_SERVICE_NOT_CONFIGURED",
                message="RECOMMENDATION_SERVICE_URL chưa được cấu hình. Vui lòng liên hệ admin."
            )

        # Retry logic: 2 retries with exponential backoff for HF Spaces cold start
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    resp = await client.post(
                        f"{service_url}/recommend",
                        json=student_data
                    )
                    resp.raise_for_status()
                    return resp.json()
            except httpx.TimeoutException:
                if attempt < max_retries:
                    wait_time = 2 ** attempt * 5  # 5s, 10s
                    logger.warning(f"AI service timeout (attempt {attempt + 1}), retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    raise APIException(
                        status_code=504,
                        code="AI_SERVICE_TIMEOUT",
                        message="AI service không phản hồi sau nhiều lần thử. Có thể đang cold start."
                    )
            except httpx.HTTPStatusError as e:
                logger.error(f"AI service error: {e.response.status_code} — {e.response.text}")
                raise APIException(
                    status_code=502,
                    code="AI_SERVICE_ERROR",
                    message=f"AI service trả về lỗi: {e.response.status_code}"
                )
            except httpx.ConnectError:
                raise APIException(
                    status_code=503,
                    code="AI_SERVICE_UNREACHABLE",
                    message="Không thể kết nối tới AI service. Kiểm tra URL và trạng thái HF Space."
                )

    # ─── Core Logic ───────────────────────────────────────────────────

    async def generate_recommendation(self, db: Session, student_id: UUID) -> RecommendationLog:
        """Generate a recommendation for a single student using the real AI service."""
        # 1. Aggregate student data from DB
        skill_scores = self.get_student_skill_scores(db, student_id)
        enrollment = self.get_student_enrollment_data(db, student_id)
        target = self.get_student_target(db, student_id)
        days_enrolled = enrollment.get("days_enrolled", 0)
        attendance_rate = enrollment.get("attendance_rate", 0.0)
        
        # 1b. Query AI feedback from past tests
        recent_ai_feedback = self.get_recent_ai_feedback(db, student_id)
        
        # 1c. Pre-detect weakest skill for test suggestion (simple heuristic)
        weakest_skill = min(skill_scores, key=skill_scores.get) if skill_scores else "unknown"
        difficulty = "easy"
        if skill_scores:
            weakest_score = skill_scores.get(weakest_skill, 0)
            if weakest_score >= 6.0:
                difficulty = "hard"
            elif weakest_score >= 4.0:
                difficulty = "medium"
        
        suggested_test_ids = self.get_suggested_test_ids(db, student_id, weakest_skill, difficulty)
        
        student_data = {
            "student_id": str(student_id),
            "skill_scores": skill_scores,
            "score_history": self.get_score_history(db, student_id),
            "attendance_rate": attendance_rate,
            "days_enrolled": days_enrolled,
            "target_band": target.get("target_band"),
            "target_cefr": target.get("target_cefr"),
            "exam_type": "ielts",
            "days_since_last_activity": self.get_days_since_last_activity(db, student_id),
            "recent_ai_feedback": recent_ai_feedback,
            "suggested_test_ids": suggested_test_ids
        }
        
        # 2. Call real AI service (no mock)
        ai_resp = await self.call_ai_service(student_data)
        
        # 3. Save log to DB
        log = RecommendationLog(
            student_id=student_id,
            skill_scores=skill_scores,
            attendance_rate=attendance_rate,
            target_band=target.get("target_band"),
            target_cefr=target.get("target_cefr"),
            predicted_band=ai_resp.get("predicted_band"),
            predicted_cefr=ai_resp.get("predicted_cefr"),
            weakest_skill=ai_resp.get("weakest_skill"),
            estimated_weeks=ai_resp.get("estimated_weeks"),
            recommendation_type=ai_resp.get("recommendation_type"),
            recommendation_data=ai_resp.get("recommendation_data"),
            learning_path=ai_resp.get("learning_path")
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    async def generate_batch(self, db: Session, student_ids: List[UUID]) -> Dict[str, int]:
        """
        Generate recommendations for multiple students in parallel.
        Uses asyncio.gather with semaphore to limit concurrent AI calls.
        """
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent AI calls
        generated = 0
        errors = 0
        error_details = []

        async def _generate_one(sid: UUID):
            nonlocal generated, errors
            async with semaphore:
                try:
                    await self.generate_recommendation(db, sid)
                    generated += 1
                except Exception as e:
                    errors += 1
                    error_details.append({"student_id": str(sid), "error": str(e)})
                    logger.error(f"Batch recommendation error for {sid}: {e}")

        await asyncio.gather(*[_generate_one(sid) for sid in student_ids])

        return {
            "generated": generated,
            "errors": errors,
            "total": len(student_ids),
            "error_details": error_details[:10]  # Cap at 10 for response size
        }

    async def get_today(self, db: Session, student_id: UUID) -> dict:
        """Get today's recommendation. Check cache → DB → generate new."""
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()
        cache_key = f"rec:{student_id}:{today}"
        
        # 1. Check Redis cache
        if redis_manager.redis_client:
            try:
                cached = await redis_manager.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")

        # 2. Check DB for today's recommendation
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        log = db.query(RecommendationLog).filter(
            RecommendationLog.student_id == student_id,
            RecommendationLog.generated_at >= start_of_day
        ).order_by(desc(RecommendationLog.generated_at)).first()

        if not log:
            # 3. Generate new recommendation from AI service
            log = await self.generate_recommendation(db, student_id)
            
        result = {
            "id": str(log.id),
            "student_id": str(log.student_id),
            "generated_at": log.generated_at.isoformat() if log.generated_at else None,
            "is_read": log.is_read,
            "skill_scores": log.skill_scores,
            "attendance_rate": float(log.attendance_rate) if log.attendance_rate else None,
            "target_band": float(log.target_band) if log.target_band else None,
            "target_cefr": log.target_cefr,
            "predicted_band": float(log.predicted_band) if log.predicted_band else None,
            "predicted_cefr": log.predicted_cefr,
            "weakest_skill": log.weakest_skill,
            "estimated_weeks": log.estimated_weeks,
            "recommendation_type": log.recommendation_type,
            "recommendation_data": log.recommendation_data,
            "learning_path": log.learning_path
        }

        # 4. Cache to Redis (TTL 24h)
        if redis_manager.redis_client:
            try:
                await redis_manager.redis_client.setex(cache_key, 86400, json.dumps(result))
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
                
        return {"data": result}


recommendation_service = RecommendationService()
