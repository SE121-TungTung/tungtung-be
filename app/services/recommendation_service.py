import json
import httpx
import asyncio
from datetime import datetime
from uuid import UUID
from typing import Dict, List, Any

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models.academic import ClassEnrollment, Class, Course
from app.models.session_attendance import ClassSession
from app.models.test import TestAttempt, TestResponse, QuestionBank, AttemptStatus
from app.models.user import User
from app.models.recommendation import RecommendationLog
from app.core.config import settings
from app.core.redis import redis_manager

class RecommendationService:
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
            days_enrolled = (datetime.now(enrollment.enrollment_date.tzinfo) - enrollment.enrollment_date).days

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
            return -1 # never active
            
        last_activity = max(times)
        return (datetime.now(last_activity.tzinfo) - last_activity).days

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

    async def call_ai_service(self, student_data: Dict[str, Any]) -> Dict[str, Any]:
        """Proxy call to AI service"""
        service_url = getattr(settings, 'RECOMMENDATION_SERVICE_URL', None)
        if not service_url:
            # Fallback for dev without URL
            return self._mock_ai_response()

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{service_url}/recommend",
                json=student_data
            )
            resp.raise_for_status()
            return resp.json()
            
    def _mock_ai_response(self) -> Dict[str, Any]:
        return {
          "predicted_band": 6.5,
          "predicted_cefr": "B2",
          "weakest_skill": "writing",
          "estimated_weeks": 12,
          "confidence": 0.82,
          "recommendation_type": "daily_practice",
          "recommendation_data": {
            "title": "Mock Recommendation",
            "skill": "writing",
            "tips": ["Tip 1"],
            "materials": []
          },
          "learning_path": {
            "estimated_weeks": 12,
            "milestones": []
          },
          "nudge": None
        }

    async def generate_recommendation(self, db: Session, student_id: UUID) -> RecommendationLog:
        # 1. Aggregate
        skill_scores = self.get_student_skill_scores(db, student_id)
        enrollment = self.get_student_enrollment_data(db, student_id)
        target = self.get_student_target(db, student_id)
        days_enrolled = enrollment.get("days_enrolled", 0)
        attendance_rate = enrollment.get("attendance_rate", 0.0)
        
        student_data = {
            "student_id": str(student_id),
            "skill_scores": skill_scores,
            "score_history": self.get_score_history(db, student_id),
            "attendance_rate": attendance_rate,
            "days_enrolled": days_enrolled,
            "target_band": target.get("target_band"),
            "target_cefr": target.get("target_cefr"),
            "exam_type": "ielts",
            "recent_ai_feedback": [] # Optional based on requirements
        }
        
        # 2. Call AI
        ai_resp = await self.call_ai_service(student_data)
        
        # 3. Save Log
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

    async def get_today(self, db: Session, student_id: UUID) -> dict:
        today = datetime.utcnow().date().isoformat()
        cache_key = f"rec:{student_id}:{today}"
        
        # 1. Check Redis
        if redis_manager.redis_client:
            try:
                cached = await redis_manager.redis_client.get(cache_key)
                if cached:
                    return json.loads(cached)
            except Exception as e:
                print(f"Redis get error: {e}")

        # 2. Check DB
        # Check if already generated today
        start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        log = db.query(RecommendationLog).filter(
            RecommendationLog.student_id == student_id,
            RecommendationLog.generated_at >= start_of_day
        ).order_by(desc(RecommendationLog.generated_at)).first()

        if not log:
            # 3. If not found -> generate
            log = await self.generate_recommendation(db, student_id)
            
        result = {
            "id": str(log.id),
            "student_id": str(log.student_id),
            "generated_at": log.generated_at.isoformat() if log.generated_at else None,
            "is_read": log.is_read,
            "skill_scores": log.skill_scores,
            "predicted_band": float(log.predicted_band) if log.predicted_band else None,
            "predicted_cefr": log.predicted_cefr,
            "weakest_skill": log.weakest_skill,
            "estimated_weeks": log.estimated_weeks,
            "recommendation_type": log.recommendation_type,
            "recommendation_data": log.recommendation_data,
            "learning_path": log.learning_path
        }

        # Cache to Redis
        if redis_manager.redis_client:
            try:
                await redis_manager.redis_client.setex(cache_key, 86400, json.dumps(result))
            except Exception as e:
                print(f"Redis set error: {e}")
                
        return {"data": result}

recommendation_service = RecommendationService()
