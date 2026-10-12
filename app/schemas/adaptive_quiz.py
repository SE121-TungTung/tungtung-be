"""Pydantic schemas for Adaptive Quiz (CAT & IRT)."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class StartSessionRequest(BaseModel):
    skill_area: str = Field(..., description="Skill area for test: reading or listening")
    max_items: Optional[int] = Field(20, ge=5, le=40, description="Max questions in session")


class ThetaHistoryPoint(BaseModel):
    item_position: int
    theta: float
    se: float
    is_correct: Optional[bool] = None
    question_id: Optional[str] = None


class AdaptiveSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    skill_area: str
    theta_initial: float
    theta_current: float
    theta_final: Optional[float] = None
    se_current: float
    se_final: Optional[float] = None
    items_administered: int
    max_items: int
    stop_reason: Optional[str] = None
    estimated_band: Optional[float] = None
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    theta_history: List[Dict[str, Any]] = []


class NextQuestionResponse(BaseModel):
    question_id: UUID
    item_position: int
    title: str
    question_text: str
    question_type: str
    skill_area: str
    options: Optional[Any] = None
    audio_url: Optional[str] = None
    image_url: Optional[str] = None
    current_theta: float
    current_se: float
    items_administered: int
    max_items: int


class SubmitResponseRequest(BaseModel):
    question_id: UUID
    response_data: Any = Field(..., description="Student response, e.g. option ID, text, etc.")
    time_spent_seconds: Optional[int] = Field(None, ge=0)


class SubmitResponseResponse(BaseModel):
    item_position: int
    is_correct: bool
    correct_answer: Optional[str] = None
    explanation: Optional[str] = None
    theta_before: float
    theta_after: float
    se_before: float
    se_after: float
    is_finished: bool
    stop_reason: Optional[str] = None
    estimated_band: Optional[float] = None


class FinishSessionResponse(BaseModel):
    id: UUID
    status: str
    theta_final: float
    se_final: float
    estimated_band: float
    items_administered: int
    stop_reason: str
    started_at: datetime
    completed_at: datetime
    theta_history: List[Dict[str, Any]]


class QuestionIRTRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    question_text: str
    question_type: str
    skill_area: str
    difficulty_level: Optional[str] = None
    irt_discrimination: float
    irt_difficulty: float
    irt_guessing: float
    irt_calibrated: bool
    irt_calibrated_at: Optional[datetime] = None
    is_cat_eligible: bool
    usage_count: int


class UpdateQuestionIRTRequest(BaseModel):
    irt_discrimination: float = Field(..., ge=0.1, le=4.0, description="Discrimination parameter a")
    irt_difficulty: float = Field(..., ge=-4.0, le=4.0, description="Difficulty parameter b")
    irt_guessing: float = Field(..., ge=0.0, le=0.5, description="Guessing parameter c")
    is_cat_eligible: Optional[bool] = True


class CalibrationStatsResponse(BaseModel):
    total_questions: int
    calibrated_count: int
    cat_eligible_count: int
    calibration_rate: float
    reading: Dict[str, int]
    listening: Dict[str, int]
    avg_difficulty: float
    avg_discrimination: float


class TriggerCalibrateRequest(BaseModel):
    min_responses: Optional[int] = Field(50, ge=10, description="Minimum responses required to calibrate item")


class TriggerCalibrateResponse(BaseModel):
    calibrated_items_count: int
    message: str
    timestamp: datetime
