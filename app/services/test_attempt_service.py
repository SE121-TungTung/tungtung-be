# app/services/test_attempt_service.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from uuid import UUID
from datetime import datetime, timezone

from app.models.test import Test, TestAttempt, TestQuestion, TestResponse as ORMTestResponse
from app.models.test import QuestionBank, AttemptStatus, TestResponse
from sqlalchemy import func
from app.schemas.test_attempt import (
    StartAttemptResponse,
    SubmitAttemptRequest,
    SubmitAttemptResponse,
    QuestionResult
)
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

    def submit_attempt(self, db: Session, payload: SubmitAttemptRequest, attempt_id: UUID):
    # 1. Load attempt
        attempt = db.query(TestAttempt).filter(
            TestAttempt.id == attempt_id,
            TestAttempt.deleted_at.is_(None)
        ).first()

        if not attempt:
            raise HTTPException(status_code=404, detail="Attempt not found")

        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise HTTPException(
                status_code=400,
                detail=f"Attempt status is {attempt.status}, cannot submit"
            )

        # 2. Load test & all test questions
        test = db.query(Test).filter(Test.id == attempt.test_id).first()
        if not test:
            raise HTTPException(status_code=404, detail="Test not found")

        tqs = (
            db.query(TestQuestion)
            .filter(TestQuestion.test_id == test.id)
            .order_by(TestQuestion.order_number.asc())
            .all()
        )

        # Prepare response mapping
        resp_map = {str(r.question_id): r for r in payload.responses}

        total_score = 0.0
        question_results = []
        any_manual = False

        # ENUM MAPPING
        AUTO_TYPES = {
            "multiple_choice",
            "true_false",
            "short_answer",
            "fill_in_blank",
            "listening",
            "reading_comprehension",
            "matching",
            "ordering",
            "drag_and_drop"
        }
        MANUAL_TYPES = {"essay", "speaking"}

        # Loop through test questions
        for tq in tqs:
            qb: QuestionBank = (
                db.query(QuestionBank)
                .filter(QuestionBank.id == tq.question_id)
                .first()
            )

            # Normalize enum
            qt_raw = qb.question_type
            qt = (
                qt_raw.value.lower().strip()
                if isinstance(qt_raw, enum.Enum)
                else str(qt_raw).lower().strip()
            )

            is_auto = qt in AUTO_TYPES
            is_manual = qt in MANUAL_TYPES

            qid = str(tq.question_id)

            # CASE 1 — Student answered
            if qid in resp_map:
                r = resp_map[qid]

                student_text = r.response_text
                student_data = r.response_data
                time_spent = r.time_spent_seconds

                is_correct = None
                points_earned = 0.0
                auto_graded = False
                feedback = None

                # AUTO GRADE
                if is_auto:
                    auto_graded = True

                    # Uniform scoring value
                    max_points = float(tq.points or qb.points or 0)

                    # AUTO RULES
                    if qt in ["multiple_choice", "true_false", "short_answer", "fill_in_blank", "listening", "reading_comprehension"]:
                        if qb.correct_answer:
                            is_correct = (
                                student_text is not None
                                and student_text.strip().lower() == qb.correct_answer.strip().lower()
                            )
                        else:
                            is_correct = False

                    elif qt == "matching":
                        is_correct = student_data == qb.correct_answer_data

                    elif qt == "ordering":
                        is_correct = student_data == qb.correct_order

                    elif qt == "drag_and_drop":
                        is_correct = student_data == qb.correct_positions

                    points_earned = max_points if is_correct else 0.0

                # MANUAL GRADE
                elif is_manual:
                    auto_graded = False
                    is_correct = None
                    points_earned = 0.0
                    feedback = "Awaiting manual grading"
                    any_manual = True

                # Save response
                db.add(TestResponse(
                    attempt_id=attempt.id,
                    question_id=tq.question_id,
                    response_text=student_text,
                    response_data=student_data,
                    time_spent_seconds=time_spent,
                    is_correct=is_correct,
                    points_earned=points_earned
                ))

                question_results.append(QuestionResult(
                    question_id=tq.question_id,
                    answered=True,
                    is_correct=is_correct,
                    points_earned=points_earned,
                    max_points=float(tq.points or qb.points or 0),
                    auto_graded=auto_graded,
                    feedback=feedback
                ))

                total_score += points_earned

            # CASE 2 — Student did NOT answer
            else:
                max_points = float(tq.points or qb.points or 0)

                if is_auto:
                    is_correct = False
                    points_earned = 0.0
                    auto_graded = True
                    feedback = "no response"
                else:
                    is_correct = None
                    points_earned = 0.0
                    auto_graded = False
                    feedback = "no response"
                    any_manual = True

                question_results.append(QuestionResult(
                    question_id=tq.question_id,
                    answered=False,
                    is_correct=is_correct,
                    points_earned=0.0,
                    max_points=max_points,
                    auto_graded=auto_graded,
                    feedback=feedback
                ))

        # Compute percentage
        max_total = sum(float(tq.points or 0) for tq in tqs)

        attempt.total_score = total_score
        attempt.percentage_score = (
            round((total_score / max_total) * 100, 2) if max_total > 0 else 0
        )
        attempt.passed = attempt.percentage_score >= float(test.passing_score)

        # Final status
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






attempt_service = AttemptService()
