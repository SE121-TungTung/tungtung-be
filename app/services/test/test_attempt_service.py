# app/services/test_attempt_service.py
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from uuid import UUID
from datetime import datetime, timezone

from app.models.test import (
    Test, TestAttempt, TestQuestion, 
    TestResponse,
    QuestionBank, AttemptStatus, QuestionType
)
from app.services.test.ai_grade import AIGradeService
from sqlalchemy import func
from app.schemas.test.test_attempt import (
    StartAttemptResponse,
    SubmitAttemptRequest,
    SubmitAttemptResponse,
    QuestionResult
)
from app.services.cloudinary import upload_and_save_metadata
from app.models.file_upload import UploadType, AccessLevel
import enum

class AttemptService:
    def start_attempt(self, db: Session, test_id: UUID, student_id: UUID) -> StartAttemptResponse:
        # Load test
        test: Test = db.query(Test).filter(Test.id == test_id, Test.deleted_at.is_(None)).first()
        if not test:
            raise HTTPException(status_code=404, detail="Test not found")

        # Check if test is currently available (start/end)
        now = datetime.now(timezone.utc)
        if test.start_time and now < test.start_time:
            raise HTTPException(status_code=400, detail="Test not started yet")
        if test.end_time and now > test.end_time:
            raise HTTPException(status_code=400, detail="Test ended")

        # Count previous attempts (committed)
        prev_attempts = (
            db.query(TestAttempt)
              .filter(TestAttempt.test_id == test_id, TestAttempt.student_id == student_id)
              .order_by(TestAttempt.attempt_number.desc())
              .with_for_update(read=True)  # optional, may help concurrency
              .all()
        )
        last_number = prev_attempts[0].attempt_number if prev_attempts else 0

        # Enforce max_attempts
        if last_number >= (test.max_attempts or 1):
            # If last attempt exists and is in_progress, return it; otherwise block
            last_attempt = prev_attempts[0] if prev_attempts else None
            if last_attempt and last_attempt.status == AttemptStatus.IN_PROGRESS:
                return StartAttemptResponse(
                    attempt_id=last_attempt.id,
                    test_id=test.id,
                    attempt_number=last_attempt.attempt_number,
                    started_at=last_attempt.started_at,
                )
            raise HTTPException(status_code=400, detail="Max attempts reached")

        # Create new attempt
        attempt_number = last_number + 1
        new_attempt = TestAttempt(
            test_id=test.id,
            student_id=student_id,
            attempt_number=attempt_number,
            started_at=datetime.now(timezone.utc),
            status=AttemptStatus.IN_PROGRESS
        )
        db.add(new_attempt)
        db.commit()
        db.refresh(new_attempt)

        return StartAttemptResponse(
            attempt_id=new_attempt.id,
            test_id=new_attempt.test_id,
            attempt_number=new_attempt.attempt_number,
            started_at=new_attempt.started_at,
        )

    async def submit_attempt(
        self,
        db: Session,
        payload: SubmitAttemptRequest,
        attempt_id: UUID
    ):
        try:
            # =========================
            # 1. Load attempt
            # =========================
            attempt = (
                db.query(TestAttempt)
                .filter(
                    TestAttempt.id == attempt_id,
                    TestAttempt.deleted_at.is_(None)
                )
                .first()
            )

            if not attempt:
                raise HTTPException(404, "Attempt not found")

            if attempt.status != AttemptStatus.IN_PROGRESS:
                raise HTTPException(
                    400,
                    f"Attempt status is {attempt.status}, cannot submit"
                )

            # =========================
            # 2. Load test & questions
            # =========================
            test = db.query(Test).filter(Test.id == attempt.test_id).first()
            if not test:
                raise HTTPException(404, "Test not found")

            test_questions = (
                db.query(TestQuestion)
                .filter(TestQuestion.test_id == test.id)
                .order_by(TestQuestion.order_number.asc())
                .all()
            )

            resp_map = {str(r.question_id): r for r in payload.responses}

            total_score = 0.0
            question_results: list[QuestionResult] = []
            any_manual = False

            ai_service = AIGradeService()

            # =========================
            # 3. Loop questions
            # =========================
            for tq in test_questions:
                qb: QuestionBank = (
                    db.query(QuestionBank)
                    .filter(QuestionBank.id == tq.question_id)
                    .first()
                )

                qid = str(tq.question_id)
                max_points = float(tq.points or qb.points or 0)

                # normalize enum
                qt = qb.question_type
                if isinstance(qt, enum.Enum):
                    qt = qt.value

                # =========================
                # CASE 1 — answered
                # =========================
                if qid in resp_map:
                    r = resp_map[qid]

                    student_text = r.response_text
                    student_data = r.response_data
                    time_spent = r.time_spent_seconds

                    is_correct = None
                    points_earned = 0.0
                    auto_graded = False
                    feedback = None

                    # -------------------------
                    # AUTO GRADE
                    # -------------------------
                    if qt in {
                        QuestionType.MULTIPLE_CHOICE.value,
                        QuestionType.TRUE_FALSE.value,
                        QuestionType.SHORT_ANSWER.value,
                        QuestionType.FILL_IN_BLANK.value,
                        QuestionType.LISTENING.value,
                        QuestionType.READING.value,
                        QuestionType.MATCHING.value,
                        QuestionType.ORDERING.value,
                        QuestionType.DRAG_AND_DROP.value,
                    }:
                        auto_graded = True

                        if qb.correct_answer:
                            is_correct = (
                                student_text is not None
                                and student_text.strip().lower()
                                == qb.correct_answer.strip().lower()
                            )
                        else:
                            is_correct = False

                        points_earned = max_points if is_correct else 0.0

                    # -------------------------
                    # AI GRADE — WRITING
                    # -------------------------
                    elif qt == QuestionType.ESSAY.value:
                        auto_graded = True

                        task_type = 1
                        if qb.extra_metadata and isinstance(qb.extra_metadata, dict):
                            task_type = qb.extra_metadata.get("writing_task", 1)

                        ai_result = await ai_service.ai_grade_writing(
                            question=qb,
                            task_type=task_type,
                            answer=student_text
                        )

                        raw = ai_result["raw"]

                        feedback = raw.get("detailedFeedback")

                    # -------------------------
                    # MANUAL — SPEAKING
                    # -------------------------
                    elif qt == QuestionType.SPEAKING.value:
                        auto_graded = False
                        any_manual = True
                        feedback = "Awaiting speaking submission"

                    else:
                        raise HTTPException(
                            400,
                            f"Unsupported question type: {qt}"
                        )

                    # Save response
                    db.add(
                        TestResponse(
                            attempt_id=attempt.id,
                            question_id=tq.question_id,
                            response_text=student_text,
                            response_data=student_data,
                            time_spent_seconds=time_spent,
                            is_correct=is_correct,
                            points_earned=points_earned,
                            auto_graded=auto_graded,
                            feedback=feedback
                        )
                    )

                    question_results.append(
                        QuestionResult(
                            question_id=tq.question_id,
                            answered=True,
                            is_correct=is_correct,
                            points_earned=points_earned,
                            max_points=max_points,
                            auto_graded=auto_graded,
                            feedback=feedback
                        )
                    )

                    total_score += points_earned

                # =========================
                # CASE 2 — not answered
                # =========================
                else:
                    auto_graded = qt != QuestionType.SPEAKING.value
                    if qt == QuestionType.SPEAKING.value:
                        any_manual = True

                    question_results.append(
                        QuestionResult(
                            question_id=tq.question_id,
                            answered=False,
                            is_correct=None,
                            points_earned=0.0,
                            max_points=max_points,
                            auto_graded=auto_graded,
                            feedback="no response"
                        )
                    )

            # =========================
            # 4. Finalize attempt
            # =========================
            max_total = sum(float(tq.points or 0) for tq in test_questions)

            attempt.total_score = total_score
            attempt.percentage_score = (
                round((total_score / max_total) * 100, 2)
                if max_total > 0
                else 0
            )
            attempt.passed = (
                attempt.percentage_score >= float(test.passing_score)
            )

            if any_manual:
                attempt.status = AttemptStatus.SUBMITTED
            else:
                attempt.status = AttemptStatus.GRADED
                attempt.graded_at = func.now()

            db.commit()
            db.refresh(attempt)

            return SubmitAttemptResponse(
                attempt_id=attempt.id,
                status=attempt.status,
                total_score=float(attempt.total_score or 0),
                percentage_score=float(attempt.percentage_score or 0),
                passed=attempt.passed,
                graded_at=attempt.graded_at,
                question_results=question_results
            )
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Submission failed: {str(e)}")
    
    async def submit_speaking(
        self,
        db: Session,
        attempt_id: UUID,
        question_id: UUID,
        audio_file: UploadFile,
        user_id: UUID
    ):
        # 1. Load attempt
        attempt = db.query(TestAttempt).filter(
            TestAttempt.id == attempt_id
        ).first()

        if not attempt:
            raise HTTPException(404, "Attempt not found")

        if attempt.status not in {
            AttemptStatus.IN_PROGRESS,
            AttemptStatus.SUBMITTED
        }:
            raise HTTPException(400, "Invalid attempt status")

        # 2. Validate question
        tq = db.query(TestQuestion).filter(
            TestQuestion.test_id == attempt.test_id,
            TestQuestion.question_id == question_id
        ).first()

        if not tq:
            raise HTTPException(400, "Question not in this test")

        question = db.query(QuestionBank).filter(
            QuestionBank.id == question_id
        ).first()

        if not question or question.question_type != QuestionType.SPEAKING.value:
            raise HTTPException(400, "Not a speaking question")

        # 3. Upload audio to Cloudinary + save metadata
        file_meta = await upload_and_save_metadata(
            db=db,
            uploaded_file=audio_file,
            user_id=user_id,
            folder="speaking_answers",
            upload_type_value=UploadType.AUDIO.value,
            access_level_value=AccessLevel.PRIVATE.value
        )

        # 4. AI grading
        ai_service = AIGradeService()

        ai_result = await ai_service.ai_grade_speaking(
            question=question,
            audio_file_path=file_meta.file_path   # 🔥 URL Cloudinary
        )

        raw = ai_result["raw"]
        ai_score = float(raw.get("overallScore", 0))

        max_points = float(tq.points or question.points or 0)
        points_earned = round((ai_score / 9.0) * max_points, 2)

        # 5. Save / update TestResponse
        response = db.query(TestResponse).filter(
            TestResponse.attempt_id == attempt.id,
            TestResponse.question_id == question_id
        ).first()

        response_data = {
            "file_upload_id": str(file_meta.id),
            "audio_url": file_meta.file_path,
            "ai_raw": raw
        }

        if response:
            response.response_data = response_data
            response.points_earned = points_earned
            response.ai_feedback = raw.get("detailedFeedback")
        else:
            response = TestResponse(
                attempt_id=attempt.id,
                question_id=question_id,
                response_data=response_data,
                points_earned=points_earned,
                auto_graded=True,
                feedback=raw.get("detailedFeedback")
            )
            db.add(response)

        # 6. Update attempt score (KHÔNG set GRADED)
        attempt.total_score = (attempt.total_score or 0) + points_earned
        attempt.status = AttemptStatus.SUBMITTED

        db.commit()

        return {
            "question_id": question_id,
            "points_earned": points_earned,
            "max_points": max_points,
            "audio_url": file_meta.file_path,
            "ai_score": ai_score,
            "transcript": raw.get("transcript"),
            "feedback": raw.get("shortFeedback")
        }
    
    def get_attempt_detail(self, db: Session, attempt_id: UUID, user_id: UUID):
        # 1. Lấy Attempt + Join Test để lấy title
        attempt = db.query(TestAttempt).join(Test).filter(
            TestAttempt.id == attempt_id
        ).first()
        
        if not attempt:
            raise HTTPException(404, "Attempt not found")
        
        # 2. Check quyền xem (User chính chủ hoặc Admin/Teacher)
        if attempt.student_id != user_id:
            # Có thể check thêm role teacher ở đây nếu cần
            raise HTTPException(403, "Not authorized to view this attempt")

        responses = (
            db.query(TestResponse)
            .join(QuestionBank)
            .filter(TestResponse.attempt_id == attempt_id)
            .all()
        )

        # 4. Build response
        details_list = []
        for resp in responses:
            details_list.append({
                "question_id": resp.question_id,
                "question_text": resp.question.question_text,
                "user_answer": resp.response_text,
                "ai_score": float(resp.ai_score or 0),
                "ai_feedback": resp.ai_feedback,
                "max_points": float(resp.question.points or 0)
            })
        
        return {
            "id": attempt.id,
            "test_id": attempt.test_id,
            "test_title": attempt.test.title,
            "student_id": attempt.student_id,
            "start_time": attempt.started_at,  # ✅ Sửa field name
            "end_time": attempt.submitted_at,   # ✅ Sửa field name
            "total_score": float(attempt.total_score or 0),
            "status": attempt.status.value,
            "details": details_list
        }


attempt_service = AttemptService()
