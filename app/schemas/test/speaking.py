# app/schemas/test/speaking.py
"""
Schemas for Speaking Test with Pre-Upload approach
Created: 2026-01-04
"""

from uuid import UUID
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

# ============================================================
# PRE-UPLOAD RESPONSE
# ============================================================

class PreUploadResponse(BaseModel):
    """Response after uploading a single audio file"""
    file_upload_id: UUID
    audio_url: str
    question_id: UUID
    file_size: int  # bytes
    duration_seconds: Optional[int] = None
    uploaded_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "file_upload_id": "123e4567-e89b-12d3-a456-426614174000",
                "audio_url": "https://res.cloudinary.com/.../audio.mp3",
                "question_id": "123e4567-e89b-12d3-a456-426614174001",
                "file_size": 1024000,
                "duration_seconds": 45,
                "uploaded_at": "2026-01-04T10:00:00Z"
            }
        }

# ============================================================
# BATCH SUBMIT REQUEST
# ============================================================

class SpeakingResponseItem(BaseModel):
    """Single speaking response with pre-uploaded file"""
    question_id: UUID
    file_upload_id: UUID
    duration_seconds: Optional[int] = None
    flagged_for_review: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "question_id": "123e4567-e89b-12d3-a456-426614174000",
                "file_upload_id": "123e4567-e89b-12d3-a456-426614174100",
                "duration_seconds": 45,
                "flagged_for_review": False
            }
        }

class BatchSubmitSpeakingRequest(BaseModel):
    """Batch submit request with pre-uploaded file IDs"""
    responses: List[SpeakingResponseItem] = Field(
        ...,
        min_length=1,
        description="List of speaking responses with file_upload_ids"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "responses": [
                    {
                        "question_id": "q1-uuid",
                        "file_upload_id": "file1-uuid",
                        "duration_seconds": 30
                    },
                    {
                        "question_id": "q2-uuid",
                        "file_upload_id": "file2-uuid",
                        "duration_seconds": 45
                    }
                ]
            }
        }

# ============================================================
# BATCH SUBMIT RESPONSE
# ============================================================

class QuestionGradingResult(BaseModel):
    """AI grading result for individual question"""
    question_id: UUID
    question_part: str  # "SPEAKING_PART_1", "SPEAKING_PART_2", "SPEAKING_PART_3"
    question_text: Optional[str] = None
    
    # Audio info
    audio_url: str
    duration_seconds: Optional[int] = None
    
    # AI Grading Results
    ai_band_score: Optional[float] = None
    ai_rubric_scores: Optional[Dict[str, float]] = None
    ai_feedback: Optional[str] = None
    ai_transcript: Optional[str] = None
    ai_points_earned: Optional[float] = None
    
    # Processing status
    processed: bool = True
    error_message: Optional[str] = None
    
    # Points
    max_points: float
    
    class Config:
        from_attributes = True

class OverallSpeakingScores(BaseModel):
    """Overall speaking scores following IELTS rubric"""
    
    # IELTS Speaking Criteria (0-9 band scale)
    fluency_coherence: Optional[float] = Field(
        None, 
        ge=0, 
        le=9,
        description="Fluency and Coherence score"
    )
    lexical_resource: Optional[float] = Field(
        None,
        ge=0,
        le=9, 
        description="Lexical Resource (Vocabulary) score"
    )
    grammatical_range: Optional[float] = Field(
        None,
        ge=0,
        le=9,
        description="Grammatical Range and Accuracy score"
    )
    pronunciation: Optional[float] = Field(
        None,
        ge=0,
        le=9,
        description="Pronunciation score"
    )
    
    # Overall band (average of 4 criteria, rounded to 0.5)
    overall_band: Optional[float] = Field(
        None,
        ge=0,
        le=9,
        description="Overall speaking band score"
    )
    
    # Breakdown by part (for reference)
    part_1_avg_band: Optional[float] = None
    part_2_avg_band: Optional[float] = None
    part_3_avg_band: Optional[float] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "fluency_coherence": 7.0,
                "lexical_resource": 7.5,
                "grammatical_range": 7.0,
                "pronunciation": 7.5,
                "overall_band": 7.5,
                "part_1_avg_band": 7.0,
                "part_2_avg_band": 7.5,
                "part_3_avg_band": 7.5
            }
        }

class BatchSubmitSpeakingResponse(BaseModel):
    """Response after batch speaking submission"""
    
    # Attempt info
    attempt_id: UUID
    test_id: UUID
    submitted_at: datetime
    
    # Processing summary
    total_questions: int
    processed_count: int
    failed_count: int
    
    # Detailed results per question
    question_results: List[QuestionGradingResult]
    
    # Overall AI assessment
    ai_overall_scores: Optional[OverallSpeakingScores] = None
    ai_overall_feedback: Optional[str] = None
    
    # Scoring (converted from band scores)
    ai_total_points: Optional[float] = None
    max_total_points: float
    
    # Status
    status: str  # "SUBMITTED", "PENDING_TEACHER_REVIEW"
    requires_teacher_review: bool = True
    
    # Time taken
    processing_time_seconds: Optional[float] = None
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "attempt_id": "attempt-uuid",
                "test_id": "test-uuid",
                "submitted_at": "2026-01-04T10:05:00Z",
                "total_questions": 6,
                "processed_count": 6,
                "failed_count": 0,
                "question_results": [],
                "ai_overall_scores": {
                    "overall_band": 7.5
                },
                "ai_total_points": 8.3,
                "max_total_points": 10.0,
                "status": "SUBMITTED",
                "requires_teacher_review": True
            }
        }