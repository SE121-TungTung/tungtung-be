from uuid import UUID
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime

class StartAttemptResponse(BaseModel):
    attempt_id: UUID
    test_id: UUID
    attempt_number: int
    started_at: datetime

    model_config = {
        "from_attributes": True
    }

# --- Request: Submit attempt ---
class QuestionSubmitItem(BaseModel):
    question_id: UUID
    # either response_text (short/essay) or selected option keys in response_data (MCQ)
    response_text: Optional[str] = None
    response_data: Optional[Any] = None
    time_spent_seconds: Optional[int] = None
    
    flagged_for_review: Optional[bool] = False


class SubmitAttemptRequest(BaseModel):
    responses: List[QuestionSubmitItem]

# --- Response: after submit ---
class QuestionResult(BaseModel):
    question_id: UUID
    answered: bool
    is_correct: Optional[bool] = None
    auto_graded: bool

    points_earned: float = 0.0
    max_points: float
    band_score: Optional[float]  # Nếu là Writing/Speaking
    
    rubric_scores: Optional[dict] = None

    # AI grading (always present if ai_grading_enabled)
    ai_points_earned: Optional[float] = None
    ai_band_score: Optional[float] = None
    ai_rubric_scores: Optional[dict] = None
    ai_feedback: Optional[str] = None
    
    # Teacher override (only if teacher graded)
    teacher_points_earned: Optional[float] = None
    teacher_band_score: Optional[float] = None
    teacher_rubric_scores: Optional[dict] = None
    teacher_feedback: Optional[str] = None

class SubmitAttemptResponse(BaseModel):
    attempt_id: UUID
    submitted_at: datetime
    time_taken_seconds: int

    status: str
    total_score: float
    percentage_score: float
    band_score: Optional[float] = None
    passed: Optional[bool] = None
    graded_at: Optional[datetime] = None
    graded_by: Optional[UUID] = None
    question_results: List[QuestionResult]

    ai_feedback: Optional[dict] = None      
    teacher_feedback: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

class QuestionResultDetail(BaseModel):
    question_id: UUID
    
    # Student Response
    audio_response_url: Optional[str] = None
    user_answer: Optional[str] = None # Text response (nếu có)
    
    # Scoring
    is_correct: Optional[bool] = None
    points_earned: float
    max_points: float
    auto_graded: bool
    
    # AI Info
    ai_score: Optional[float] = None
    ai_feedback: Optional[str] = None
    
    # Teacher Info
    teacher_score: Optional[float] = None
    teacher_feedback: Optional[str] = None
    
    # Metadata
    time_spent_seconds: Optional[int] = None
    flagged_for_review: bool = False

# Schema chi tiết lịch sử làm bài (Dùng cho API get_attempt_detail)
class TestAttemptDetailResponse(BaseModel):
    id: UUID
    test_id: UUID
    test_title: str
    student_id: UUID
    
    start_time: datetime
    end_time: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    time_taken_seconds: Optional[int] = None
    
    total_score: Optional[float] = None
    percentage_score: Optional[float] = None
    band_score: Optional[float] = None
    passed: Optional[bool] = None
    status: str
    
    # Feedback Overall
    ai_feedback: Optional[str] = None # JSON feedback
    teacher_feedback: Optional[str] = None # String feedback
    graded_by: Optional[UUID] = None
    
    # Security info
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Danh sách kết quả từng câu
    details: List[QuestionResultDetail]

    model_config = {
        "from_attributes": True
    }