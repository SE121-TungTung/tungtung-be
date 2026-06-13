# app/services/test/speaking_service.py
"""
Speaking Test Service - Pre-Upload + Batch Submit Approach
Created: 2026-01-04
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException, BackgroundTasks
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
from app.services.audit_log_service import audit_service
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
        user_id: UUID,
        background_tasks: BackgroundTasks = None
    ) -> BatchSubmitSpeakingResponse:
        """
        Batch submit all speaking responses using pre-uploaded file IDs
        
        Main workflow:
        1. Validate all file_upload_ids and questions
        2. Save responses to DB immediately (so they exist for final submit)
        3. Enqueue AI grading in the background
        4. Return early with empty grading info
        
        Args:
            db: Database session
            attempt_id: Test attempt ID
            request: Batch request with file_upload_ids
            user_id: Student user ID
            background_tasks: BackgroundTasks object
            
        Returns:
            Immediate response with processing set to false
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
        
        # Get max points for each question
        test_questions = db.query(TestQuestion).filter(
            TestQuestion.test_id == attempt.test_id,
            TestQuestion.question_id.in_(question_ids)
        ).all()
        
        points_map = {tq.question_id: float(tq.points) for tq in test_questions}
        total_max_points = sum(points_map.values())
        
        # ============================================================
        # 3. SAVE RESPONSES TO DB IMMEDIATELY
        # ============================================================
        
        question_results = []
        response_items_map = {r.question_id: r for r in request.responses}
        
        for question in questions:
            response_item = response_items_map[question.id]
            file_meta = file_map[response_item.file_upload_id]
            max_points = points_map.get(question.id, 0.0)
            
            # Save or update response immediately with empty grading details
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
                    processed=False  # AI grading will happen in background
                )
            )
        
        db.commit()
        
        # ============================================================
        # 4. ENQUEUE AI GRADING IN BACKGROUND
        # ============================================================
        
        file_ids_map = {str(r.question_id): str(r.file_upload_id) for r in request.responses}
        response_items_flagged = {str(r.question_id): bool(r.flagged_for_review) for r in request.responses}
        
        if background_tasks:
            background_tasks.add_task(
                self._grade_speaking_in_background,
                attempt_id=attempt_id,
                question_ids=question_ids,
                file_ids_map=file_ids_map,
                response_items_flagged=response_items_flagged,
                user_id=user_id
            )
        else:
            # Fallback to fire-and-forget async task
            asyncio.create_task(
                self._grade_speaking_in_background(
                    attempt_id=attempt_id,
                    question_ids=question_ids,
                    file_ids_map=file_ids_map,
                    response_items_flagged=response_items_flagged,
                    user_id=user_id
                )
            )
        
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
                "processed_count": len(question_results),
                "failed_count": 0,
                "ai_total_points": 0.0,
                "background_grading": True
            }
        )
        
        db.commit()
        
        # ============================================================
        # 5. RETURN RESPONSE
        # ============================================================
        
        processing_time = time.time() - start_time
        
        return BatchSubmitSpeakingResponse(
            attempt_id=attempt_id,
            test_id=attempt.test_id,
            submitted_at=datetime.now(timezone.utc),
            total_questions=len(question_results),
            processed_count=len(question_results),
            failed_count=0,
            question_results=question_results,
            ai_overall_scores=None,
            ai_total_points=0.0,
            ai_rubric_scores=None,
            max_total_points=total_max_points,
            status=attempt.status.value,
            requires_teacher_review=True,
            processing_time_seconds=round(processing_time, 2)
        )

    async def _grade_speaking_in_background(
        self,
        attempt_id: UUID,
        question_ids: List[UUID],
        file_ids_map: Dict[str, str],  # question_id_str -> file_upload_id_str
        response_items_flagged: Dict[str, bool],  # question_id_str -> flagged
        user_id: UUID
    ):
        """
        Background task to perform AI grading for speaking questions.
        Uses a fresh database session to avoid closed connection errors.
        """
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            # 1. Fetch attempt
            attempt = db.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
            if not attempt:
                return
            
            # 2. Fetch questions
            questions = db.query(QuestionBank).filter(
                QuestionBank.id.in_(question_ids)
            ).all()
            question_map = {q.id: q for q in questions}
            
            # 3. Fetch file uploads
            file_ids = list(file_ids_map.values())
            files = db.query(FileUpload).filter(
                FileUpload.id.in_(file_ids)
            ).all()
            file_map = {str(f.id): f for f in files}
            
            # 4. Get points for each question
            test_questions = db.query(TestQuestion).filter(
                TestQuestion.test_id == attempt.test_id,
                TestQuestion.question_id.in_(question_ids)
            ).all()
            points_map = {tq.question_id: float(tq.points) for tq in test_questions}
            
            # 5. Create grading tasks
            grading_tasks = []
            valid_questions = []
            
            for q_id in question_ids:
                question = question_map.get(q_id)
                f_id = file_ids_map.get(str(q_id))
                file_meta = file_map.get(str(f_id))
                if not question or not file_meta:
                    continue
                
                valid_questions.append(question)
                grading_tasks.append(
                    self._grade_single_question(
                        question=question,
                        audio_url=file_meta.file_path,
                        file_upload_id=file_meta.id
                    )
                )
            
            # Run parallel AI grading
            grading_results = await asyncio.gather(
                *grading_tasks,
                return_exceptions=True
            )
            
            # 6. Save results
            for i, question in enumerate(valid_questions):
                grading_result = grading_results[i]
                f_id = file_ids_map.get(str(question.id))
                file_meta = file_map.get(str(f_id))
                max_points = points_map.get(question.id, 0.0)
                flagged = response_items_flagged.get(str(question.id), False)
                
                if isinstance(grading_result, Exception):
                    # Save response without AI results
                    continue
                
                # Extract AI results
                raw = grading_result.get("raw", {})
                ai_band = float(raw.get("overallScore", 0))
                
                # Map rubric scores supporting both snake_case and camelCase
                criteria = raw.get("criteriaScores", {}) or raw.get("rubricScores", {}) or {}
                val_fc = float(criteria.get("fluencyCoherence") or criteria.get("fluency_coherence") or 0.0)
                val_lr = float(criteria.get("lexicalResource") or criteria.get("lexical_resource") or 0.0)
                val_gr = float(criteria.get("grammaticalRange") or criteria.get("grammatical_range") or 0.0)
                val_pr = float(criteria.get("pronunciation") or 0.0)
                ai_rubric = {
                    "fluency_coherence": val_fc,
                    "fluencyCoherence": val_fc,
                    "lexical_resource": val_lr,
                    "lexicalResource": val_lr,
                    "grammatical_range": val_gr,
                    "grammaticalRange": val_gr,
                    "pronunciation": val_pr
                }
                
                ai_feedback = raw.get("detailedFeedback")
                ai_transcript = raw.get("transcript")
                refined_transcript = raw.get("refinedTranscript")
                better_version = raw.get("betterVersion")
                pronunciation_breakdown = raw.get("pronunciationBreakdown", [])
                
                # Convert band score to points
                ai_points = 0.0
                if ai_band > 0:
                    ai_points = round((ai_band / 9.0) * max_points, 2)
                
                # Save Response to DB
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
                    flagged=flagged,
                    refined_transcript=refined_transcript,
                    better_version=better_version,
                    pronunciation_breakdown=pronunciation_breakdown
                )
            
            db.commit()
        except Exception as e:
            print(f"Error in background speaking grading task: {e}")
        finally:
            db.close()
    
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
        flagged: bool = False,
        refined_transcript: str = None,
        better_version: str = None,
        pronunciation_breakdown: List = None
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
        if refined_transcript is not None:
            response_data["refined_transcript"] = refined_transcript
        if better_version is not None:
            response_data["better_version"] = better_version
        if pronunciation_breakdown is not None:
            response_data["pronunciation_breakdown"] = pronunciation_breakdown
        
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