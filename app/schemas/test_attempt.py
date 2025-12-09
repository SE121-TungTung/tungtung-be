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
    feedback: Optional[str] = None

class SubmitAttemptResponse(BaseModel):
    attempt_id: UUID
    status: str
    total_score: float
    percentage_score: float
    passed: Optional[bool] = None
    graded_at: Optional[datetime] = None
    question_results: List[QuestionResult]

    model_config = {
        "from_attributes": True
    }