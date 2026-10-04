from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field
from app.models.pronunciation import TargetType
from app.schemas.base_schema import ApiResponse, PaginationResponse


# ---------------------------------------------------------------------------
# Nested Sub-schemas
# ---------------------------------------------------------------------------

class ComponentScores(BaseModel):
    accuracy: Optional[float] = Field(None, description="Score 0-100")
    fluency: Optional[float] = Field(None, description="Score 0-100")
    completeness: Optional[float] = Field(None, description="Score 0-100")
    prosody: Optional[float] = Field(None, description="Score 0-100")
    stress: Optional[float] = Field(None, description="Score 0-100")
    intonation: Optional[float] = Field(None, description="Score 0-100")
    rhythm: Optional[float] = Field(None, description="Score 0-100")

    model_config = {"from_attributes": True}


class PhonemeResult(BaseModel):
    phoneme: str
    score: float
    status: str
    expected: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class PronunciationPracticeCreateResponse(BaseModel):
    """Phản hồi sau khi hoàn tất lượt luyện phát âm (POST /practices)."""
    id: UUID
    student_id: UUID
    target_text: str
    target_type: TargetType
    target_ipa: Optional[str] = None
    actual_ipa: Optional[str] = None
    overall_score: float
    component_scores: Optional[Dict[str, Any]] = None
    phoneme_results: Optional[List[Dict[str, Any]]] = None
    error_summary: Optional[Dict[str, Any]] = None
    feedback_text: Optional[str] = None
    processing_time_ms: Optional[int] = None
    audio_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PronunciationPracticeDetailResponse(BaseModel):
    """Chi tiết đầy đủ của 1 lượt luyện tập (GET /practices/{id})."""
    id: UUID
    student_id: UUID
    target_text: str
    target_type: TargetType
    target_ipa: Optional[str] = None
    actual_ipa: Optional[str] = None
    overall_score: float
    component_scores: Optional[Dict[str, Any]] = None
    phoneme_results: Optional[List[Dict[str, Any]]] = None
    error_summary: Optional[Dict[str, Any]] = None
    feedback_text: Optional[str] = None
    processing_time_ms: Optional[int] = None
    audio_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PronunciationPracticeListItem(BaseModel):
    """Mục tóm tắt trong danh sách lịch sử luyện tập (GET /practices)."""
    id: UUID
    target_text: str
    target_type: TargetType
    target_ipa: Optional[str] = None
    actual_ipa: Optional[str] = None
    overall_score: float
    component_scores: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class WeakPhonemeItem(BaseModel):
    phoneme: str
    error_count: int
    total_count: int
    accuracy_rate: float


class RecentTrendItem(BaseModel):
    date: str
    avg_score: float
    count: int


class PronunciationStatsResponse(BaseModel):
    """Thống kê tổng hợp luyện phát âm (GET /practices/stats)."""
    total_practices: int
    average_score: float
    practice_by_type: Dict[str, int]
    weak_phonemes: List[WeakPhonemeItem]
    recent_trend: List[RecentTrendItem]

    model_config = {"from_attributes": True}


class PronunciationStreakResponse(BaseModel):
    """Thông tin chuỗi ngày luyện tập liên tục (GET /practices/streak)."""
    current_streak: int
    longest_streak: int
    last_practice_date: Optional[date] = None
    today_practiced: bool
    active_days_this_month: int

    model_config = {"from_attributes": True}


class DrillSuggestionsResponse(BaseModel):
    """Gợi ý từ/câu luyện tập theo chủ đề IELTS (GET /drill-suggestions)."""
    topic: str
    items: List[str]


# ---------------------------------------------------------------------------
# Typed response wrappers
# ---------------------------------------------------------------------------

PronunciationPracticeApiResponse = ApiResponse[PronunciationPracticeDetailResponse]
PronunciationPracticeListResponse = PaginationResponse[PronunciationPracticeListItem]
PronunciationStatsApiResponse = ApiResponse[PronunciationStatsResponse]
PronunciationStreakApiResponse = ApiResponse[PronunciationStreakResponse]
PronunciationDrillSuggestionsApiResponse = ApiResponse[DrillSuggestionsResponse]


# ---------------------------------------------------------------------------
# Phase 2 — Assessment + Mastery schemas
# ---------------------------------------------------------------------------

class AssessmentItemRequest(BaseModel):
    """Một mục trong bài placement test."""
    target_text: str
    target_type: str = "word"
    overall_score: float
    phoneme_results: Optional[List[Dict[str, Any]]] = None


class AssessmentSubmitRequest(BaseModel):
    """Request body cho POST /pronunciation/assessment."""
    items: List[AssessmentItemRequest] = Field(..., min_length=1, max_length=20)
    accent: str = "US"


class AssessmentResponse(BaseModel):
    """Response cho kết quả placement test."""
    id: UUID
    cefr_level: Optional[str] = None
    ielts_band_estimate: Optional[float] = None
    weak_phonemes: List[str]
    strong_phonemes: List[str]
    assessment_items: Optional[List[Dict[str, Any]]] = None
    retake_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class PhonemeMasteryItem(BaseModel):
    """Một phoneme trong mastery map."""
    phoneme: str
    mastery_level: int
    avg_score: Optional[float] = None
    total_attempts: int
    status: str


class MasteryMapResponse(BaseModel):
    phonemes: List[PhonemeMasteryItem]


class ReviewQueueItem(BaseModel):
    phoneme: str
    mastery_level: int
    last_score: Optional[float] = None
    interval_days: int
    next_review_at: Optional[str] = None


class ReviewQueueResponse(BaseModel):
    due_phonemes: List[ReviewQueueItem]
    count: int


class MissionItem(BaseModel):
    """Một nhiệm vụ luyện tập trong ngày."""
    mission_id: str
    type: str  # "review" | "weak_practice" | "new_phoneme" | "sentence"
    label: str
    description: str
    target_text: str
    target_type: str = "word"
    phoneme: Optional[str] = None
    priority: int = 0
    completed: bool = False


class DailyMissionsResponse(BaseModel):
    """Response cho GET /pronunciation/missions/today."""
    date: str
    missions: List[MissionItem]
    total_missions: int
    completed_count: int
    streak_bonus: bool = False
