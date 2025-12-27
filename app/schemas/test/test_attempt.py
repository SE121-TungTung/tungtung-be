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
    points_earned: float
    max_points: float
    auto_graded: bool

    ai_score: Optional[float] = None
    ai_feedback: Optional[str] = None

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

    model_config = {
        "from_attributes": True
    }