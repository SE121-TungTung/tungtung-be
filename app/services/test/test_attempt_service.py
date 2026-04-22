# app/services/test/test_attempt_service.py

import math

from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, UploadFile
from uuid import UUID
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.exceptions import APIException
from app.models.user import User, UserRole
from app.models.test import (
    Test, TestAttempt, TestQuestion, 
    TestResponse, QuestionBank, 
    AttemptStatus, QuestionType
)
from app.schemas.base_schema import PaginationMetadata, PaginationResponse
from app.schemas.base_schema import PaginationResponse
from app.services.test.ai_grade import ai_grade_service
from app.schemas.test.test_attempt import (
    StartAttemptResponse,
    SubmitAttemptRequest,
    SubmitAttemptResponse,
    QuestionResult,
    GradeAttemptRequest,
    TestAttemptSummaryResponse
)
from app.schemas.test.test_read import TestAttemptDetailResponse, QuestionResultResponse

from app.services.audit_log_service import audit_service
from app.models.audit_log import AuditAction

from app.services.notification_service import notification_service
from app.schemas.notification import NotificationCreate
from app.models.notification import NotificationType, NotificationPriority
from app.services.test.test_grader_service import get_grader

class AttemptService:
    
    # ============================================================
    # 1. START ATTEMPT
    # ============================================================
    def start_attempt(self, db: Session, test_id: UUID, student_id: UUID) -> StartAttemptResponse:
        # Load test
        test: Test = db.query(Test).filter(Test.id == test_id, Test.deleted_at.is_(None)).first()
        if not test:
            raise HTTPException(status_code=404, detail="Test not found")

        # Check start/end time
        now = datetime.now(timezone.utc)
        if test.start_time and now < test.start_time:
            raise HTTPException(status_code=400, detail="Test not started yet")
        if test.end_time and now > test.end_time:
            raise HTTPException(status_code=400, detail="Test has ended")

        # Check max attempts
        count = db.query(TestAttempt).filter(
            TestAttempt.test_id == test_id,
            TestAttempt.student_id == student_id
        ).count()
        
        if count >= test.max_attempts:
            raise HTTPException(status_code=400, detail="Max attempts reached")

        # Check for in-progress attempt
        existing = db.query(TestAttempt).filter(
            TestAttempt.test_id == test_id,
            TestAttempt.student_id == student_id,
            TestAttempt.status == AttemptStatus.IN_PROGRESS
        ).first()
        
        if existing:
            return StartAttemptResponse(
                attempt_id=existing.id,
                test_id=existing.test_id,
                started_at=existing.started_at,
                attempt_number=existing.attempt_number
            )

        # Create new attempt
        attempt = TestAttempt(
            test_id=test_id,
            student_id=student_id,
            attempt_number=count + 1,
            status=AttemptStatus.IN_PROGRESS,
            started_at=now
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)

        return StartAttemptResponse(
            attempt_id=attempt.id,
            test_id=attempt.test_id,
            started_at=attempt.started_at,
            attempt_number=attempt.attempt_number
        )

    # ============================================================
    # 2. SUBMIT ATTEMPT (Reading, Listening, Writing)
    # ============================================================
    async def submit_attempt(
        self, 
        db: Session, 
        attempt_id: UUID, 
        data: SubmitAttemptRequest,
        user_id: UUID
    ) -> SubmitAttemptResponse:
        
        # 1. Validate Attempt
        attempt = db.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
        if not attempt:
            raise HTTPException(404, "Attempt not found")
        if attempt.student_id != user_id:
            raise HTTPException(403, "Not authorized")
        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise HTTPException(400, "Attempt already submitted or expired")

        attempt.submitted_at = datetime.now(timezone.utc)
        attempt.time_taken_seconds = int((attempt.submitted_at - attempt.started_at).total_seconds())
        
        # 2. Prepare Data
        # Fetch all questions in this test to get max_points and type
        # Join TestQuestion to get overridden points
        questions_query = (
            db.query(QuestionBank, TestQuestion.points)
            .join(TestQuestion, TestQuestion.question_id == QuestionBank.id)
            .filter(TestQuestion.test_id == attempt.test_id)
            .all()
        )
        
        # Map: question_id -> (QuestionObj, max_points)
        q_map = {q.id: (q, float(pts)) for q, pts in questions_query}
        
        # Map: user submission dict
        answers_map = {item.question_id: item for item in data.responses}

        total_points_earned = 0.0
        max_total_points = 0.0
        
        any_manual_grading_required = False
        question_results = []

        # 3. Process Each Question
        for q_id, (qb, max_points) in q_map.items():
            submission = answers_map.get(q_id)
            
            # Check if response exists (e.g. from Speaking submission)
            existing_resp = db.query(TestResponse).filter(
                TestResponse.attempt_id == attempt.id,
                TestResponse.question_id == q_id
            ).first()
            
            # --- Default Values ---
            points_earned = 0.0
            is_correct = None
            auto_graded = False
            
            ai_points_earned = None
            ai_band_score = None
            ai_rubric_scores = None
            ai_feedback = None
            
            flagged = submission.flagged_for_review if submission else False
            student_data = submission.response_data if submission else None
            
            # Extract text answer if applicable (for AI grading/Feedback)
            student_text = submission.response_text if submission else ""

            # --- A. AUTO GRADING (Reading / Listening) ---
            if QuestionType.is_auto_gradable(qb.question_type):
                auto_graded = True
                if submission and qb.correct_answer:
                    # Normalize submission structure
                    user_answer = None
                    if isinstance(student_data, dict):
                        user_answer = student_data.get("selected")
                    else:
                        user_answer = student_text
                    
                    is_correct = self._check_answer_correctness(
                        user_answer=user_answer,
                        correct_answer=qb.correct_answer,
                        question_type=qb.question_type
                    )
                    points_earned = max_points if is_correct else 0.0
                
                total_points_earned += points_earned
                max_total_points += max_points

            # --- B. MANUAL / AI GRADING (Writing) ---
            elif qb.question_type in [QuestionType.WRITING_TASK_1, QuestionType.WRITING_TASK_2]:
                auto_graded = False
                any_manual_grading_required = True
                max_total_points += max_points # Vẫn cộng vào tổng điểm tối đa
                
                if submission and student_text.strip():
                    # Determine task type
                    task_type = 2 if qb.question_type == QuestionType.WRITING_TASK_2 else 1
                    
                    # Call AI Service
                    try:
                        ai_result = await ai_grade_service.ai_grade_writing(
                            question=qb,
                            task_type=task_type,
                            answer=student_text
                        )
                        raw = ai_result.get("raw", {})
                        
                        # Extract AI Results
                        ai_band_score = float(raw.get("overallScore", 0))
                        ai_rubric_scores = raw.get("rubricScores", {})
                        ai_feedback = raw.get("detailedFeedback")
                        
                        # Convert Band to Points (Scale 0-9 -> 0-max_points)
                        if ai_band_score > 0:
                            ai_points_earned = round((ai_band_score / 9.0) * max_points, 2)
                        
                        # NOTE: Points earned tạm thời để 0 chờ Teacher duyệt
                        points_earned = 0 
                        
                    except Exception as e:
                        print(f"AI Grading Error for Q {q_id}: {e}")
                        # Không fail request, chỉ log lỗi, để teacher chấm tay hoàn toàn

            # --- C. SPEAKING (Should be handled in separate API, but handle fallback) ---
            elif qb.question_type in [
                QuestionType.SPEAKING_PART_1, 
                QuestionType.SPEAKING_PART_2, 
                QuestionType.SPEAKING_PART_3
            ]:
                auto_graded = False
                any_manual_grading_required = True
                max_total_points += max_points
                # Speaking responses are usually submitted via submit_speaking endpoint
                # If they exist here, it might be just text notes or placeholders

            # 4. Save Response to DB
            if existing_resp:
                # Update logic if needed, usually we overwrite or skip
                pass 
            else:
                new_resp = TestResponse(
                    attempt_id=attempt.id,
                    question_id=q_id,
                    response_text=student_text,
                    response_data=student_data,
                    
                    # Auto grade fields
                    is_correct=is_correct,
                    points_earned=points_earned,
                    auto_graded=auto_graded,
                    
                    # AI fields (Suggestions)
                    ai_points_earned=ai_points_earned,
                    ai_band_score=ai_band_score,
                    ai_rubric_scores=ai_rubric_scores,
                    ai_feedback=ai_feedback,
                    
                    flagged_for_review=flagged
                )
                db.add(new_resp)
                
            # 5. Add to Result List for Response
            question_results.append(
                QuestionResult(
                    question_id=q_id,
                    answered=submission is not None,
                    is_correct=is_correct,
                    auto_graded=auto_graded,
                    
                    points_earned=points_earned,
                    max_points=max_points,
                    band_score=None,
                    
                    # AI info
                    ai_points_earned=ai_points_earned,
                    ai_band_score=ai_band_score,
                    ai_rubric_scores=ai_rubric_scores,
                    ai_feedback=ai_feedback
                )
            )

        # 6. Finalize Attempt Status & Score
        ai_feedback, graded_by, teacher_feedback = self.finalize_score(attempt, total_points_earned, max_total_points, any_manual_grading_required)

        audit_service.log(
            db=db,
            user_id=user_id,
            action=AuditAction.SUBMIT,
            table_name="test_attempts",
            record_id=attempt.id,
            new_values={
                "attempt_id": str(attempt.id),
                "student_id": str(attempt.student_id),
                "status": attempt.status.value,
                "total_score": float(attempt.total_score or 0),
                "percentage_score": float(attempt.percentage_score or 0)
            }
        )

        db.commit()
        db.refresh(attempt)

        return SubmitAttemptResponse(
            attempt_id=attempt.id,
            submitted_at=attempt.submitted_at,
            time_taken_seconds=int((attempt.submitted_at - attempt.started_at).total_seconds()),
            
            status=attempt.status.value,
            total_score=float(attempt.total_score or 0),
            percentage_score=float(attempt.percentage_score or 0),
            band_score=float(attempt.band_score) if attempt.band_score else None,
            passed=attempt.passed,
            
            graded_at=attempt.graded_at,
            graded_by=graded_by,
            
            # Feedback (Teacher feedback will be null initially)
            ai_feedback=ai_feedback, 
            teacher_feedback=teacher_feedback,
            
            question_results=question_results
        )

    # ============================================================
    # 4. GET ATTEMPT DETAIL
    # ============================================================
    def get_attempt_detail(self, db: Session, attempt_id: UUID, user_id: UUID) -> TestAttemptDetailResponse:
        """
        Get detailed attempt information including all responses
        """
        # 1. Load attempt with test info
        attempt = db.query(TestAttempt).options(
            joinedload(TestAttempt.test),
            joinedload(TestAttempt.responses).joinedload(TestResponse.question)
        ).filter(TestAttempt.id == attempt_id).first()
        
        if not attempt:
            raise HTTPException(404, "Attempt not found")
        
        # 2. Authorization
        if attempt.student_id != user_id:
            raise HTTPException(403, "Not authorized to view this attempt")

        return self._build_full_attempt_response(db=db, attempt=attempt)
    
    def get_attempt_detail_for_teacher(
        self,
        db: Session,
        attempt_id: UUID
    ):
        attempt = db.query(TestAttempt).options(
            joinedload(TestAttempt.test),
            joinedload(TestAttempt.responses).joinedload(TestResponse.question)
        ).filter(TestAttempt.id == attempt_id).first()

        if not attempt:
            raise HTTPException(404, "Attempt not found")

        return self._build_full_attempt_response(db=db, attempt=attempt)

    
    def list_attempts_for_teacher(
        self,
        db: Session,
        test_id: UUID,
        user_id: UUID,
        user_role: UserRole = None,
        skip: int = 0,    
        limit: int = 20   
    ):
        # ============================================================
        # 1. KIỂM TRA SỰ TỒN TẠI VÀ QUYỀN SỞ HỮU CỦA TEST
        # ============================================================
        test = db.query(Test).filter(Test.id == test_id, Test.deleted_at.is_(None)).first()
        
        if not test:
            raise APIException(
                status_code=404, 
                code="TEST_NOT_FOUND", 
                message="Bài thi không tồn tại hoặc đã bị xóa."
            )

        if user_role == UserRole.TEACHER:
            if test.created_by != user_id:
                raise APIException(
                    status_code=403, 
                    code="FORBIDDEN_TEST_ACCESS", 
                    message="Bạn không có quyền xem danh sách làm bài của bài thi không do bạn tạo."
                )

        # ============================================================
        # 2. KHỞI TẠO BASE QUERY 
        # ============================================================
        base_query = (
            db.query(
                TestAttempt,
                User.first_name,
                User.last_name
            )
            .join(User, User.id == TestAttempt.student_id)
            .filter(
                TestAttempt.test_id == test_id,
                TestAttempt.deleted_at.is_(None)
            )
        )

        # ============================================================
        # 3. ĐẾM TỔNG SỐ VÀ TÍNH METADATA
        # ============================================================
        total = base_query.count()
        page = (skip // limit) + 1 if limit > 0 else 1
        total_pages = math.ceil(total / limit) if limit > 0 else 1

        meta = PaginationMetadata(
            page=page, limit=limit, total=total, total_pages=total_pages
        )

        # ============================================================
        # 4. TRUY VẤN DỮ LIỆU CÓ PHÂN TRANG
        # ============================================================
        rows = (
            base_query
            .order_by(TestAttempt.started_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        # ============================================================
        # 5. CHUẨN HÓA DATA THEO SCHemas
        # ============================================================
        results = []
        for attempt, first_name, last_name in rows:
            results.append(TestAttemptSummaryResponse(
                id=attempt.id,
                student_id=attempt.student_id,
                student_name=f"{first_name} {last_name}".strip(),
                status=attempt.status.value if hasattr(attempt.status, 'value') else attempt.status,
                score=attempt.band_score,
                started_at=attempt.started_at,
                submitted_at=attempt.submitted_at,
            ))

        return PaginationResponse(
            data=results,
            meta=meta
        )
    
    async def grade_attempt(
        self,
        db: Session,
        attempt_id: UUID,
        teacher_id: UUID,
        data: GradeAttemptRequest
    ):
        attempt = (
            db.query(TestAttempt)
            .filter(
                TestAttempt.id == attempt_id,
                TestAttempt.status == AttemptStatus.SUBMITTED
            )
            .first()
        )

        if not attempt:
            raise HTTPException(404, "Attempt not found or not ready for grading")

        total_points = 0
        max_points = 0

        # Fetch all TestQuestion records once
        test_questions = db.query(TestQuestion).filter(
            TestQuestion.test_id == attempt.test_id
        ).all()
        points_map = {tq.question_id: float(tq.points) for tq in test_questions}
        
        # Fetch all responses once
        responses_map = {
            resp.question_id: resp 
            for resp in db.query(TestResponse).filter(
            TestResponse.attempt_id == attempt_id
            ).all()
        }
        
        for item in data.questions:
            resp = responses_map.get(item.question_id)
            if not resp:
                continue

            max_q_points = points_map.get(item.question_id, 0)
            max_points += max_q_points

            resp.teacher_points_earned = item.teacher_points_earned
            resp.teacher_band_score = item.teacher_band_score
            resp.teacher_rubric_scores = item.teacher_rubric_scores
            resp.teacher_feedback = item.teacher_feedback

            resp.points_earned = item.teacher_points_earned
            total_points += item.teacher_points_earned
        
        self.finalize_score(attempt, total_points, max_points, False)

        attempt.teacher_feedback = data.overall_feedback
        attempt.graded_by = teacher_id
        attempt.graded_at = datetime.now(timezone.utc)
        attempt.status = AttemptStatus.GRADED

        audit_service.log(
            db=db,
            user_id=teacher_id,
            action=AuditAction.GRADE,
            table_name="test_attempts",
            record_id=attempt.id,
            new_values={
                "attempt_id": str(attempt.id),
                "graded_by": str(teacher_id),
                "total_score": float(attempt.total_score or 0),
                "percentage_score": float(attempt.percentage_score or 0),
                "band_score": float(attempt.band_score or 0)
            }
        )
        
        db.commit()
        db.refresh(attempt)

        noti = NotificationCreate(
            user_id=attempt.student_id,
            title="Kết quả bài kiểm tra đã có",
            content=(
                f"Bài kiểm tra của bạn đã được chấm. "
                f"Band score: {attempt.band_score}, "
                f"{'Đạt' if attempt.passed else 'Chưa đạt'}."
            ),
            notification_type=NotificationType.GRADE_AVAILABLE,
            priority=NotificationPriority.NORMAL,
            action_url=f"/student/tests/attempts/{attempt.id}",
        )

        await notification_service.send_notification(
            db=db,
            noti_info=noti
        )

        return {
            "status": "graded",
            "attempt_id": attempt.id,
            "band_score": attempt.band_score,
            "passed": attempt.passed
        }



    # ============================================================
    # 5. HELPER METHODS
    # ============================================================
    def _check_answer_correctness(
        self,
        user_answer: Any,
        correct_answer: str,
        question_type: QuestionType
    ) -> bool:
        """
        Check if user answer is correct using the appropriate grading strategy
        """
        # 1. Lấy bộ chấm điểm tương ứng với loại câu hỏi
        grader = get_grader(question_type)
        # 2. Thực hiện chấm điểm
        return grader.check(user_answer, correct_answer)

    def _calculate_band_score(self, percentage: float) -> float:
        """
        Convert percentage to IELTS band score (0-9, step 0.5)
        Rough conversion for reading/listening simulation
        """
        if percentage < 0:
            return 0.0
        if percentage >= 100:
            return 9.0
        
        # Simple linear conversion table simulation
        # 0-9 scale mapping
        score = (percentage / 100) * 9
        
        # Round to nearest 0.5
        band = round(score * 2) / 2
        return band
    
    def finalize_score(self, attempt, total_points_earned, max_total_points, any_manual_grading_required):
        attempt.total_score = total_points_earned
        
        # Calculate percentage
        if max_total_points > 0:
            attempt.percentage_score = round((total_points_earned / max_total_points) * 100, 2)
        else:
            attempt.percentage_score = 0.0
            
        # Determine Status & Band Score
        if any_manual_grading_required:
            attempt.status = AttemptStatus.SUBMITTED # Chờ Teacher chấm tiếp
            attempt.band_score = None # Chưa có band cuối cùng
            attempt.passed = None
        else:
            # Fully auto-graded
            attempt.status = AttemptStatus.GRADED
            attempt.passed = attempt.percentage_score >= float(attempt.test.passing_score)
            # Calculate band score if applicable (Simulation)
            attempt.band_score = self._calculate_band_score(attempt.percentage_score)

        graded_by = attempt.graded_by if isinstance(attempt.graded_by, UUID) else None
        ai_feedback = attempt.ai_feedback if isinstance(attempt.ai_feedback, dict) else None
        teacher_feedback = attempt.teacher_feedback if isinstance(attempt.teacher_feedback, str) else None
        return ai_feedback,graded_by,teacher_feedback
    
    def _map_response_to_result_schema(self, resp: TestResponse, max_points: float) -> QuestionResultResponse:
        """Hàm chuẩn hóa 1 dòng dữ liệu DB thành 1 Model Pydantic"""
        q_text = resp.question.question_text if hasattr(resp, 'question') and resp.question else None
        q_type = resp.question.question_type if hasattr(resp, 'question') and resp.question else None
        q_type_str = q_type.value if hasattr(q_type, 'value') else str(q_type)

        return QuestionResultResponse(
            question_id=resp.question_id,
            question_text=q_text,
            question_type=q_type_str,
            user_answer=resp.response_text,
            response_data=resp.response_data,
            audio_response_url=resp.audio_response_url,
            is_correct=resp.is_correct,
            auto_graded=resp.auto_graded,
            
            points_earned=float(resp.points_earned or 0),
            max_points=float(max_points or 0),
            band_score=float(resp.teacher_band_score) if resp.teacher_band_score else (float(resp.ai_band_score) if resp.ai_band_score else None),
            rubric_scores=resp.teacher_rubric_scores if resp.teacher_rubric_scores else resp.ai_rubric_scores,
            
            ai_points_earned=float(resp.ai_points_earned) if resp.ai_points_earned is not None else None,
            ai_band_score=float(resp.ai_band_score) if resp.ai_band_score is not None else None,
            ai_rubric_scores=resp.ai_rubric_scores,
            ai_feedback=resp.ai_feedback,
            
            teacher_points_earned=float(resp.teacher_points_earned) if resp.teacher_points_earned is not None else None,
            teacher_band_score=float(resp.teacher_band_score) if resp.teacher_band_score is not None else None,
            teacher_rubric_scores=resp.teacher_rubric_scores,
            teacher_feedback=resp.teacher_feedback,
            
            time_spent_seconds=resp.time_spent_seconds,
            flagged_for_review=resp.flagged_for_review
        )

    def _build_full_attempt_response(self, db: Session, attempt: TestAttempt) -> TestAttemptDetailResponse:
        """Hàm duy nhất để build toàn bộ Response cho API Get Detail (O(1) memory lookup)"""
        # 1. Lấy bản đồ điểm cực nhanh (Bulk Query)
        test_questions = db.query(TestQuestion).filter(TestQuestion.test_id == attempt.test_id).all()
        points_map = {tq.question_id: float(tq.points) for tq in test_questions}
        
        # 2. Map dữ liệu
        details_list = [
            self._map_response_to_result_schema(resp, points_map.get(resp.question_id, 0.0))
            for resp in attempt.responses
        ]

        return TestAttemptDetailResponse(
            id=attempt.id,
            test_id=attempt.test_id,
            test_title=attempt.test.title if attempt.test else None,
            student_id=attempt.student_id,
            attempt_number=attempt.attempt_number, 
            started_at=attempt.started_at, 
            submitted_at=attempt.submitted_at,
            time_taken_seconds=attempt.time_taken_seconds,
            
            total_score=float(attempt.total_score or 0),
            percentage_score=float(attempt.percentage_score or 0),
            band_score=float(attempt.band_score) if attempt.band_score else None,
            passed=attempt.passed,
            status=attempt.status.value if attempt.status else None,
            
            ai_feedback=attempt.ai_feedback,
            teacher_feedback=attempt.teacher_feedback,
            graded_by=attempt.graded_by,
            ip_address=str(attempt.ip_address) if attempt.ip_address else None,
            user_agent=attempt.user_agent,
            
            details=details_list
        )


attempt_service = AttemptService()