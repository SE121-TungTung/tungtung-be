# app/services/test/test_attempt_service.py

from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, UploadFile
from uuid import UUID
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.models.test import (
    Test, TestAttempt, TestQuestion, 
    TestResponse, QuestionBank, 
    AttemptStatus, QuestionType
)
from app.services.test.ai_grade import ai_grade_service
from app.schemas.test.test_attempt import (
    StartAttemptResponse,
    SubmitAttemptRequest,
    SubmitAttemptResponse,
    QuestionResult,
    TestAttemptDetailResponse,
    QuestionResultDetail
)
from app.services.cloudinary import upload_and_save_metadata
from app.models.file_upload import UploadType, AccessLevel

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
                start_time=existing.started_at,
                remaining_seconds=self._calculate_remaining_time(existing, test)
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
            start_time=attempt.started_at,
            remaining_seconds=test.time_limit_minutes * 60 if test.time_limit_minutes else None
        )

    def _calculate_remaining_time(self, attempt: TestAttempt, test: Test) -> Optional[int]:
        if not test.time_limit_minutes:
            return None
        elapsed = (datetime.now(timezone.utc) - attempt.started_at).total_seconds()
        remaining = (test.time_limit_minutes * 60) - elapsed
        return max(0, int(remaining))

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
        answers_map = {item.question_id: item for item in data.answers}

        total_points_earned = 0.0
        max_total_points = 0.0
        
        any_manual_grading_required = False
        question_results = []

        # 3. Process Each Question
        for q_id, (qb, max_points) in q_map.items():
            submission = answers_map.get(q_id)
            
            # --- Default Values ---
            points_earned = 0.0
            is_correct = None
            auto_graded = False
            
            ai_points_earned = None
            ai_band_score = None
            ai_rubric_scores = None
            ai_feedback = None
            
            flagged = submission.flagged_for_review if submission else False
            student_data = submission.answer_data if submission else None
            
            # Extract text answer if applicable (for AI grading/Feedback)
            student_text = ""
            if student_data:
                if isinstance(student_data, dict):
                    student_text = str(student_data.get("text", "") or student_data.get("selected", ""))
                else:
                    student_text = str(student_data)

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
            # Check if response exists (e.g. from Speaking submission)
            existing_resp = db.query(TestResponse).filter(
                TestResponse.attempt_id == attempt.id,
                TestResponse.question_id == q_id
            ).first()

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
                    
                    # AI info
                    ai_points_earned=ai_points_earned,
                    ai_band_score=ai_band_score,
                    ai_rubric_scores=ai_rubric_scores,
                    ai_feedback=ai_feedback
                )
            )

        # 6. Finalize Attempt Status & Score
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
            graded_by=attempt.graded_by,
            
            # Feedback (Teacher feedback will be null initially)
            ai_feedback=attempt.ai_feedback, 
            teacher_feedback=attempt.teacher_feedback,
            
            question_results=question_results
        )

    # ============================================================
    # 3. SUBMIT SPEAKING (Audio)
    # ============================================================
    async def submit_speaking(
        self,
        db: Session,
        attempt_id: UUID,
        question_id: UUID,
        file: UploadFile,
        user_id: UUID
    ):
        # 1. Validate
        attempt = db.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
        if not attempt:
            raise HTTPException(404, "Attempt not found")
        if attempt.student_id != user_id:
            raise HTTPException(403, "Not authorized")
        
        question = db.query(QuestionBank).filter(QuestionBank.id == question_id).first()
        if not question:
            raise HTTPException(404, "Question not found")
            
        # Fix #6: Check correct Speaking types
        if question.question_type not in [
            QuestionType.SPEAKING_PART_1,
            QuestionType.SPEAKING_PART_2,
            QuestionType.SPEAKING_PART_3
        ]:
            raise HTTPException(400, "Not a speaking question")

        # 2. Upload to Cloudinary
        file_meta = await upload_and_save_metadata(
            db=db,
            file=file,
            uploader_id=user_id,
            upload_type=UploadType.ASSIGNMENT_SUBMISSION,
            access_level=AccessLevel.PRIVATE
        )

        # 3. Get Max Points for this question in this test
        tq = db.query(TestQuestion).filter(
            TestQuestion.test_id == attempt.test_id,
            TestQuestion.question_id == question_id
        ).first()
        max_points = float(tq.points) if tq else 1.0

        # 4. AI Grading
        ai_points_earned = 0
        ai_band_score = None
        ai_rubric_scores = None
        ai_feedback = None
        
        try:
            # Call AI Service (assumes it handles audio url or file)
            # Here passing file_url. AI Service needs to handle speech-to-text then grade.
            ai_result = await ai_grade_service.ai_grade_speaking(
                question=question,
                audio_url=file_meta.file_path 
            )
            raw = ai_result.get("raw", {})
            
            # Extract
            ai_band_score = float(raw.get("overallScore", 0))
            ai_rubric_scores = raw.get("rubricScores", {})
            ai_feedback = raw.get("detailedFeedback")
            
            # Convert
            if ai_band_score > 0:
                ai_points_earned = round((ai_band_score / 9.0) * max_points, 2)
                
        except Exception as e:
            print(f"AI Speaking Grade Error: {e}")

        # 5. Save/Update TestResponse
        response = db.query(TestResponse).filter(
            TestResponse.attempt_id == attempt_id,
            TestResponse.question_id == question_id
        ).first()

        response_data = {
            "file_upload_id": str(file_meta.id),
            "audio_url": file_meta.file_path
        }

        if response:
            response.response_data = response_data
            response.audio_response_url = file_meta.file_path
            
            # Update AI suggestions
            response.ai_points_earned = ai_points_earned
            response.ai_band_score = ai_band_score
            response.ai_rubric_scores = ai_rubric_scores
            response.ai_feedback = ai_feedback
            
            # Reset Manual scores (wait for teacher)
            response.points_earned = 0
            response.band_score = None
            response.auto_graded = False 
        else:
            response = TestResponse(
                attempt_id=attempt_id,
                question_id=question_id,
                response_data=response_data,
                audio_response_url=file_meta.file_path,
                
                points_earned=0, # Wait for teacher
                auto_graded=False,
                
                # AI Suggestions
                ai_points_earned=ai_points_earned,
                ai_band_score=ai_band_score,
                ai_rubric_scores=ai_rubric_scores,
                ai_feedback=ai_feedback
            )
            db.add(response)

        # 6. Update Attempt Status
        # Fix #8: Do not calculate score yet, just mark as submitted
        attempt.status = AttemptStatus.SUBMITTED
        
        db.commit()
        
        return {
            "status": "success",
            "audio_url": file_meta.file_path,
            "ai_feedback": ai_feedback,
            "ai_band_score": ai_band_score
        }

    # ============================================================
    # 4. GET ATTEMPT DETAIL
    # ============================================================
    def get_attempt_detail(self, db: Session, attempt_id: UUID, user_id: UUID) -> TestAttemptDetailResponse:
        """
        Get detailed attempt information including all responses
        """
        # 1. Load attempt with test info
        attempt = (
            db.query(TestAttempt)
            .options(joinedload(TestAttempt.test))
            .filter(TestAttempt.id == attempt_id)
            .first()
        )
        
        if not attempt:
            raise HTTPException(404, "Attempt not found")
        
        # 2. Authorization
        if attempt.student_id != user_id:
            # TODO: Add logic to allow Teachers/Admins to view
            raise HTTPException(403, "Not authorized to view this attempt")

        # 3. Load responses with Question info
        # We need max points from TestQuestion as well
        responses_query = (
            db.query(TestResponse, QuestionBank, TestQuestion.points)
            .join(QuestionBank, TestResponse.question_id == QuestionBank.id)
            .join(TestQuestion, (TestQuestion.test_id == attempt.test_id) & (TestQuestion.question_id == QuestionBank.id))
            .filter(TestResponse.attempt_id == attempt_id)
            .all()
        )

        # 4. Build response details
        details_list = []
        for resp, qb, max_pts in responses_query:
            
            # Map Response to Schema
            detail = QuestionResultDetail(
                question_id=resp.question_id,
                
                # Basic info
                audio_response_url=resp.audio_response_url,
                is_correct=resp.is_correct,
                points_earned=float(resp.points_earned or 0),
                max_points=float(max_pts or 0),
                auto_graded=resp.auto_graded,
                
                # AI Grading
                ai_score=float(resp.ai_points_earned) if resp.ai_points_earned else None,
                ai_feedback=resp.ai_feedback,
                
                # Teacher Grading
                teacher_score=float(resp.teacher_points_earned) if resp.teacher_points_earned else None,
                teacher_feedback=resp.teacher_feedback,
                
                time_spent_seconds=resp.time_spent_seconds,
                flagged_for_review=resp.flagged_for_review
            )
            details_list.append(detail)
        
        # 5. Return Full Response
        return TestAttemptDetailResponse(
            id=attempt.id,
            test_id=attempt.test_id,
            test_title=attempt.test.title,
            student_id=attempt.student_id,
            
            start_time=attempt.started_at,
            end_time=attempt.submitted_at, # Using submitted_at as end time
            
            # Fix #9: Map correct fields
            submitted_at=attempt.submitted_at,
            time_taken_seconds=attempt.time_taken_seconds,
            
            total_score=float(attempt.total_score or 0),
            percentage_score=float(attempt.percentage_score or 0),
            band_score=float(attempt.band_score) if attempt.band_score else None,
            passed=attempt.passed,
            status=attempt.status.value,
            
            # Overall Feedback
            ai_feedback=attempt.ai_feedback,
            teacher_feedback=attempt.teacher_feedback,
            graded_by=attempt.graded_by,
            
            # Security
            ip_address=str(attempt.ip_address) if attempt.ip_address else None,
            user_agent=attempt.user_agent,
            
            details=details_list
        )

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
        Check if user answer is correct based on question type
        """
        if not correct_answer:
            return False
        
        # Normalize correct answer
        correct_normalized = str(correct_answer).strip().lower()
        
        # Normalize User Answer
        if user_answer is None:
            return False
            
        # ===========================
        # MULTIPLE CHOICE
        # ===========================
        if question_type == QuestionType.MULTIPLE_CHOICE:
            if isinstance(user_answer, list):
                # Multiple answers: ["A", "B"]
                correct_list = [ans.strip().lower() for ans in correct_normalized.split(",")]
                user_list = [ans.strip().lower() for ans in user_answer]
                return set(user_list) == set(correct_list)
            else:
                # Single answer: "A"
                return str(user_answer).strip().lower() == correct_normalized
        
        # ===========================
        # TRUE/FALSE/NOT GIVEN
        # ===========================
        elif question_type in [
            QuestionType.TRUE_FALSE_NOT_GIVEN,
            QuestionType.YES_NO_NOT_GIVEN
        ]:
            user_normalized = str(user_answer).strip().lower()
            # Handle cases where frontend sends "True" or "T"
            map_val = {"t": "true", "f": "false", "ng": "not given", 
                       "y": "yes", "n": "no"}
            user_mapped = map_val.get(user_normalized, user_normalized)
            correct_mapped = map_val.get(correct_normalized, correct_normalized)
            return user_mapped == correct_mapped
        
        # ===========================
        # MATCHING (Headings, Information, Features)
        # ===========================
        elif question_type in [
            QuestionType.MATCHING_HEADINGS,
            QuestionType.MATCHING_INFORMATION,
            QuestionType.MATCHING_FEATURES
        ]:
            # Format: "A" hoặc "i" hoặc "1"
            user_normalized = str(user_answer).strip().lower()
            return user_normalized == correct_normalized
        
        # ===========================
        # SHORT ANSWER / COMPLETION
        # ===========================
        elif question_type in [
            QuestionType.SHORT_ANSWER,
            QuestionType.SENTENCE_COMPLETION,
            QuestionType.SUMMARY_COMPLETION,
            QuestionType.NOTE_COMPLETION,
            QuestionType.DIAGRAM_LABELING
        ]:
            # Flexible matching: accept variations
            user_normalized = str(user_answer).strip().lower()
            
            # Check exact match
            if user_normalized == correct_normalized:
                return True
            
            # Check if correct answer has multiple acceptable answers
            # Format: "answer1|answer2|answer3" or "answer1 / answer2"
            delimiters = ["|", "/"]
            acceptable_answers = [correct_normalized]
            
            for delim in delimiters:
                if delim in correct_normalized:
                    acceptable_answers = [
                        ans.strip() 
                        for ans in correct_normalized.split(delim)
                    ]
                    break
                    
            return user_normalized in acceptable_answers
        
        # Default: exact match
        else:
            user_normalized = str(user_answer).strip().lower()
            return user_normalized == correct_normalized

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
        # Example: 6.2 -> 6.0, 6.3 -> 6.5, 6.7 -> 6.5, 6.8 -> 7.0
        band = round(score * 2) / 2
        return band

attempt_service = AttemptService()