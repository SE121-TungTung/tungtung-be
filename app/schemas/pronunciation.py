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


# ---------------------------------------------------------------------------
# Typed response wrappers
# ---------------------------------------------------------------------------

PronunciationPracticeApiResponse = ApiResponse[PronunciationPracticeDetailResponse]
PronunciationPracticeListResponse = PaginationResponse[PronunciationPracticeListItem]
PronunciationStatsApiResponse = ApiResponse[PronunciationStatsResponse]
PronunciationStreakApiResponse = ApiResponse[PronunciationStreakResponse]
