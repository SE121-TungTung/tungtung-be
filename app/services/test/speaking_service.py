# app/services/test/speaking_service.py
"""
Speaking Test Service - Pre-Upload + Batch Submit Approach
Created: 2026-01-04
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException
from uuid import UUID
from datetime import datetime, timezone
from typing import List, Dict, Tuple
import asyncio
import time

from app.models.test import (
    TestAttempt, TestQuestion, TestResponse,
    QuestionBank, QuestionType, AttemptStatus
)
from app.models.file_upload import FileUpload
from app.services.test.ai_grade import ai_grade_service
from app.schemas.test.speaking import (
    PreUploadResponse,
    BatchSubmitSpeakingRequest,
    BatchSubmitSpeakingResponse,
    QuestionGradingResult,
    OverallSpeakingScores
)
from app.services.audit_log import audit_service
from app.models.audit_log import AuditAction

class SpeakingService:
    """
    Service for handling speaking test submissions with pre-upload approach
    
    Flow:
    1. Pre-upload: Student uploads each audio file individually
    2. Batch submit: Submit all file_upload_ids for AI grading
    3. Parallel AI grading for all questions
    4. Calculate overall scores
    5. Return comprehensive results
    """
    
    # ============================================================
    # STEP 1: PRE-UPLOAD SINGLE AUDIO
    # ============================================================
    
    async def pre_upload_audio(
        self,
        db: Session,
        attempt_id: UUID,
        question_id: UUID,
        file_meta: FileUpload,
        user_id: UUID
    ) -> PreUploadResponse:
        """
        Pre-upload single audio file for a speaking question
        
        This allows progressive upload as student records answers.
        File is saved but not yet graded.
        
        Args:
            db: Database session
            attempt_id: Test attempt ID
            question_id: Speaking question ID
            file_meta: Uploaded file metadata from Cloudinary
            user_id: Student user ID
            
        Returns:
            PreUploadResponse with file_upload_id for later submission
        """
        
        # Validate attempt
        attempt = self._validate_attempt_access(db, attempt_id, user_id)
        
        # Validate question
        question = self._validate_speaking_question(db, question_id, attempt.test_id)
        
        # Log pre-upload
        audit_service.log(
            db=db,
            user_id=user_id,
            action=AuditAction.CREATE,
            table_name="file_uploads",
            record_id=file_meta.id,
            new_values={
                "attempt_id": str(attempt_id),
                "question_id": str(question_id),
                "file_path": file_meta.file_path
            }
        )
        
        db.commit()
        
        return PreUploadResponse(
            file_upload_id=file_meta.id,
            audio_url=file_meta.file_path,
            question_id=question_id,
            file_size=file_meta.file_size or 0,
            uploaded_at=file_meta.created_at or datetime.now(timezone.utc)
        )
    
    # ============================================================
    # STEP 2: BATCH SUBMIT WITH PRE-UPLOADED FILES
    # ============================================================
    
    async def batch_submit_speaking(
        self,
        db: Session,
        attempt_id: UUID,
        request: BatchSubmitSpeakingRequest,
        user_id: UUID
    ) -> BatchSubmitSpeakingResponse:
        """
        Batch submit all speaking responses using pre-uploaded file IDs
        
        Main workflow:
        1. Validate all file_upload_ids and questions
        2. AI grade all questions in parallel
        3. Calculate overall scores
        4. Save all responses
        5. Update attempt status
        
        Args:
            db: Database session
            attempt_id: Test attempt ID
            request: Batch request with file_upload_ids
            user_id: Student user ID
            
        Returns:
            Comprehensive results with AI grading and overall scores
        """
        
        start_time = time.time()
        
        # ============================================================
        # 1. VALIDATE ATTEMPT
        # ============================================================
        
        attempt = self._validate_attempt_access(db, attempt_id, user_id)
        
        if attempt.status not in [AttemptStatus.IN_PROGRESS, AttemptStatus.SUBMITTED]:
            raise HTTPException(
                400,
                f"Cannot submit speaking for attempt with status {attempt.status.value}"
            )
        
        # ============================================================
        # 2. VALIDATE FILES & QUESTIONS
        # ============================================================
        
        # Get all file_upload_ids
        file_ids = [r.file_upload_id for r in request.responses]
        
        # Fetch files - must belong to user
        files = db.query(FileUpload).filter(
            FileUpload.id.in_(file_ids),
            FileUpload.uploaded_by == user_id
        ).all()
        
        if len(files) != len(file_ids):
            raise HTTPException(
                400,
                "Some files not found or you don't have permission"
            )
        
        file_map = {f.id: f for f in files}
        
        # Get all questions
        question_ids = [r.question_id for r in request.responses]
        questions = db.query(QuestionBank).filter(
            QuestionBank.id.in_(question_ids)
        ).all()
        
        if len(questions) != len(question_ids):
            raise HTTPException(400, "Some questions not found")
        
        # Validate all are speaking questions
        for q in questions:
            if q.question_type not in [
                QuestionType.SPEAKING_PART_1,
                QuestionType.SPEAKING_PART_2,
                QuestionType.SPEAKING_PART_3
            ]:
                raise HTTPException(
                    400,
                    f"Question {q.id} is not a speaking question (type: {q.question_type.value})"
                )
        
        question_map = {q.id: q for q in questions}
        
        # Get max points for each question
        test_questions = db.query(TestQuestion).filter(
            TestQuestion.test_id == attempt.test_id,
            TestQuestion.question_id.in_(question_ids)
        ).all()
        
        points_map = {tq.question_id: float(tq.points) for tq in test_questions}
        total_max_points = sum(points_map.values())
        
        # ============================================================
        # 3. AI GRADE ALL IN PARALLEL
        # ============================================================
        
        grading_tasks = []
        response_items_map = {r.question_id: r for r in request.responses}
        
        for question in questions:
            response_item = response_items_map[question.id]
            file_meta = file_map[response_item.file_upload_id]
            
            # Create grading task
            grading_tasks.append(
                self._grade_single_question(
                    question=question,
                    audio_url=file_meta.file_path,
                    file_upload_id=file_meta.id
                )
            )
        
        # Execute all grading in parallel (KEY PERFORMANCE OPTIMIZATION)
        grading_results = await asyncio.gather(
            *grading_tasks,
            return_exceptions=True  # Don't fail entire batch if one fails
        )
        
        # ============================================================
        # 4. PROCESS RESULTS & SAVE TO DB
        # ============================================================
        
        question_results = []
        successful_gradings = []
        failed_count = 0
        
        for i, question in enumerate(questions):
            response_item = response_items_map[question.id]
            file_meta = file_map[response_item.file_upload_id]
            grading_result = grading_results[i]
            
            max_points = points_map.get(question.id, 0)
            
            # Check if grading succeeded or failed
            if isinstance(grading_result, Exception):
                # AI Grading failed for this question
                failed_count += 1
                
                error_msg = str(grading_result)
                
                # Still save response without AI scores
                self._save_or_update_response(
                    db=db,
                    attempt_id=attempt_id,
                    question_id=question.id,
                    file_upload_id=file_meta.id,
                    audio_url=file_meta.file_path,
                    flagged=response_item.flagged_for_review
                )
                
                question_results.append(
                    QuestionGradingResult(
                        question_id=question.id,
                        question_part=question.question_type.value,
                        question_text=question.question_text,
                        audio_url=file_meta.file_path,
                        duration_seconds=response_item.duration_seconds,
                        max_points=max_points,
                        processed=False,
                        error_message=error_msg
                    )
                )
                continue
            
            # Extract AI results
            raw = grading_result.get("raw", {})
            ai_band = float(raw.get("overallScore", 0))
            ai_rubric = raw.get("rubricScores", {})
            ai_feedback = raw.get("detailedFeedback")
            ai_transcript = raw.get("transcript")
            
            # Convert band score to points (0-9 scale to 0-max_points scale)
            ai_points = 0.0
            if ai_band > 0:
                ai_points = round((ai_band / 9.0) * max_points, 2)
            
            # Collect for overall calculation
            successful_gradings.append({
                "question_type": question.question_type,
                "band_score": ai_band,
                "rubric_scores": ai_rubric,
                "points": ai_points,
                "max_points": max_points
            })
            
            # Save response to DB
            self._save_or_update_response(
                db=db,
                attempt_id=attempt_id,
                question_id=question.id,
                file_upload_id=file_meta.id,
                audio_url=file_meta.file_path,
                transcript=ai_transcript,
                ai_band_score=ai_band,
                ai_rubric_scores=ai_rubric,
                ai_feedback=ai_feedback,
                ai_points_earned=ai_points,
                flagged=response_item.flagged_for_review
            )
            
            # Add to results
            question_results.append(
                QuestionGradingResult(
                    question_id=question.id,
                    question_part=question.question_type.value,
                    question_text=question.question_text,
                    audio_url=file_meta.file_path,
                    duration_seconds=response_item.duration_seconds,
                    ai_band_score=ai_band,
                    ai_rubric_scores=ai_rubric,
                    ai_feedback=ai_feedback,
                    ai_transcript=ai_transcript,
                    ai_points_earned=ai_points,
                    max_points=max_points,
                    processed=True
                )
            )
        
        # ============================================================
        # 5. CALCULATE OVERALL SCORES
        # ============================================================
        
        overall_scores = None
        ai_total_points = 0.0
        
        if successful_gradings:
            overall_scores = self._calculate_overall_scores(successful_gradings)
            ai_total_points = sum(g["points"] for g in successful_gradings)
        
        # ============================================================
        # 6. UPDATE ATTEMPT STATUS
        # ============================================================
        
        attempt.status = AttemptStatus.SUBMITTED
        attempt.submitted_at = datetime.now(timezone.utc)
        
        # Audit log
        audit_service.log(
            db=db,
            user_id=user_id,
            action=AuditAction.SUBMIT,
            table_name="test_attempts",
            record_id=attempt.id,
            new_values={
                "speaking_submitted": True,
                "total_questions": len(question_results),
                "processed_count": len(question_results) - failed_count,
                "failed_count": failed_count,
                "ai_total_points": float(ai_total_points)
            }
        )
        
        db.commit()
        
        # ============================================================
        # 7. RETURN RESPONSE
        # ============================================================
        
        processing_time = time.time() - start_time
        
        return BatchSubmitSpeakingResponse(
            attempt_id=attempt_id,
            test_id=attempt.test_id,
            submitted_at=attempt.submitted_at,
            total_questions=len(question_results),
            processed_count=len(question_results) - failed_count,
            failed_count=failed_count,
            question_results=question_results,
            ai_overall_scores=overall_scores,
            ai_total_points=ai_total_points,
            ai_rubric_scores=ai_rubric,
            max_total_points=total_max_points,
            status=attempt.status.value,
            requires_teacher_review=True,
            processing_time_seconds=round(processing_time, 2)
        )
    
    # ============================================================
    # HELPER METHODS
    # ============================================================
    
    def _validate_attempt_access(
        self,
        db: Session,
        attempt_id: UUID,
        user_id: UUID
    ) -> TestAttempt:
        """Validate attempt exists and user has access"""
        attempt = db.query(TestAttempt).filter(
            TestAttempt.id == attempt_id
        ).first()
        
        if not attempt:
            raise HTTPException(404, "Attempt not found")
        
        if attempt.student_id != user_id:
            raise HTTPException(403, "Not authorized to access this attempt")
        
        return attempt
    
    def _validate_speaking_question(
        self,
        db: Session,
        question_id: UUID,
        test_id: UUID
    ) -> QuestionBank:
        """Validate question exists and is a speaking question"""
        question = db.query(QuestionBank).filter(
            QuestionBank.id == question_id
        ).first()
        
        if not question:
            raise HTTPException(404, f"Question {question_id} not found")
        
        if question.question_type not in [
            QuestionType.SPEAKING_PART_1,
            QuestionType.SPEAKING_PART_2,
            QuestionType.SPEAKING_PART_3
        ]:
            raise HTTPException(
                400,
                f"Question {question_id} is not a speaking question"
            )
        
        # Verify question belongs to the test
        test_question = db.query(TestQuestion).filter(
            TestQuestion.test_id == test_id,
            TestQuestion.question_id == question_id
        ).first()
        
        if not test_question:
            raise HTTPException(
                400,
                f"Question {question_id} does not belong to this test"
            )
        
        return question
    
    async def _grade_single_question(
        self,
        question: QuestionBank,
        audio_url: str,
        file_upload_id: UUID
    ) -> Dict:
        """
        AI grade single speaking question
        
        Raises exception if grading fails (caught by gather)
        """
        try:
            result = await ai_grade_service.ai_grade_speaking(
                question=question,
                audio_url=audio_url
            )
            return result
        except Exception as e:
            # Re-raise with more context
            raise Exception(
                f"AI grading failed for question {question.id}: {str(e)}"
            )
    
    def _save_or_update_response(
        self,
        db: Session,
        attempt_id: UUID,
        question_id: UUID,
        file_upload_id: UUID,
        audio_url: str,
        transcript: str = None,
        ai_band_score: float = None,
        ai_rubric_scores: Dict = None,
        ai_feedback: str = None,
        ai_points_earned: float = None,
        flagged: bool = False
    ):
        """Save or update TestResponse"""
        
        response = db.query(TestResponse).filter(
            TestResponse.attempt_id == attempt_id,
            TestResponse.question_id == question_id
        ).first()
        
        response_data = {
            "file_upload_id": str(file_upload_id),
            "audio_url": audio_url
        }
        
        if response:
            # Update existing
            response.response_data = response_data
            response.audio_response_url = audio_url
            response.response_text = transcript
            response.ai_band_score = ai_band_score
            response.ai_rubric_scores = ai_rubric_scores
            response.ai_feedback = ai_feedback
            response.ai_points_earned = ai_points_earned
            response.flagged_for_review = flagged
            response.points_earned = 0  # Wait for teacher grading
        else:
            # Create new
            response = TestResponse(
                attempt_id=attempt_id,
                question_id=question_id,
                response_data=response_data,
                audio_response_url=audio_url,
                response_text=transcript,
                points_earned=0,  # Wait for teacher
                auto_graded=False,
                ai_band_score=ai_band_score,
                ai_rubric_scores=ai_rubric_scores,
                ai_feedback=ai_feedback,
                ai_points_earned=ai_points_earned,
                flagged_for_review=flagged
            )
            db.add(response)
    
    def _calculate_overall_scores(
        self,
        gradings: List[Dict]
    ) -> OverallSpeakingScores:
        """
        Calculate overall speaking scores from individual questions
        
        IELTS Speaking scoring methodology:
        - 4 criteria: Fluency, Lexical, Grammar, Pronunciation
        - Each criterion scored 0-9
        - Overall = average of 4 criteria, rounded to nearest 0.5
        - Part scores for reference
        """
        
        # Group by part
        part_scores = {
            QuestionType.SPEAKING_PART_1: [],
            QuestionType.SPEAKING_PART_2: [],
            QuestionType.SPEAKING_PART_3: []
        }
        
        # Collect all rubric scores
        all_rubric = {
            "fluency_coherence": [],
            "lexical_resource": [],
            "grammatical_range": [],
            "pronunciation": []
        }
        
        for g in gradings:
            qtype = g["question_type"]
            band = g["band_score"]
            rubric = g.get("rubric_scores", {})
            
            # Add to part scores
            if qtype in part_scores:
                part_scores[qtype].append(band)
            
            # Collect rubric scores
            for criterion in all_rubric.keys():
                if criterion in rubric:
                    all_rubric[criterion].append(float(rubric[criterion]))
        
        # Calculate averages
        def avg(scores):
            return round(sum(scores) / len(scores), 1) if scores else None
        
        def round_to_half(score):
            """Round to nearest 0.5 (IELTS standard)"""
            if score is None:
                return None
            return round(score * 2) / 2
        
        # Part averages
        part_1_avg = avg(part_scores[QuestionType.SPEAKING_PART_1])
        part_2_avg = avg(part_scores[QuestionType.SPEAKING_PART_2])
        part_3_avg = avg(part_scores[QuestionType.SPEAKING_PART_3])
        
        # Criteria averages
        fluency = avg(all_rubric["fluency_coherence"])
        lexical = avg(all_rubric["lexical_resource"])
        grammar = avg(all_rubric["grammatical_range"])
        pronunciation = avg(all_rubric["pronunciation"])
        
        # Overall (average of 4 criteria, rounded to 0.5)
        criteria_scores = [
            s for s in [fluency, lexical, grammar, pronunciation] if s is not None
        ]
        
        overall = None
        if criteria_scores:
            raw_avg = sum(criteria_scores) / len(criteria_scores)
            overall = round_to_half(raw_avg)
        
        return OverallSpeakingScores(
            fluency_coherence=fluency,
            lexical_resource=lexical,
            grammatical_range=grammar,
            pronunciation=pronunciation,
            overall_band=overall,
            part_1_avg_band=part_1_avg,
            part_2_avg_band=part_2_avg,
            part_3_avg_band=part_3_avg
        )


# Singleton instance
speaking_service = SpeakingService()