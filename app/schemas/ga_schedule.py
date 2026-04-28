"""
GA Schedule Schemas
===================
Pydantic models for GA schedule optimizer API.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, List, Optional
from datetime import date, time, datetime
from uuid import UUID


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class GAClassPreference(BaseModel):
    """Buổi ưu thích cho 1 lớp khi chạy GA."""
    class_id: UUID
    preferred_time_period: str = Field(
        ..., pattern="^(morning|afternoon|evening)$",
        description="Buổi ưu thích: morning / afternoon / evening"
    )

class GAScheduleRequest(BaseModel):
    """Request body for running the GA schedule optimizer."""
    start_date: date = Field(..., description="Ngày bắt đầu khoảng TKB cần xếp")
    end_date: date = Field(..., description="Ngày kết thúc")
    class_ids: Optional[List[UUID]] = Field(None, description="Danh sách class cần xếp (null = tất cả active)")

    # GA Hyperparameters (with sensible defaults)
    population_size: int = Field(100, ge=10, le=500, description="Kích thước quần thể")
    generations: int = Field(300, ge=10, le=2000, description="Số thế hệ tối đa")
    crossover_rate: float = Field(0.70, ge=0.0, le=1.0, description="Tỷ lệ lai ghép")
    mutation_rate: float = Field(0.15, ge=0.0, le=1.0, description="Tỷ lệ đột biến")

    # Soft constraint weights (optional override)
    weight_consecutive_limit: float = Field(10.0, ge=0.0, description="Weight: giáo viên không dạy > 3 tiết liên tiếp")
    weight_paired_classes: float = Field(8.0, ge=0.0, description="Weight: cặp lớp cùng buổi")
    weight_time_preference: float = Field(5.0, ge=0.0, description="Weight: xếp đúng buổi sáng/chiều")
    weight_room_utilization: float = Field(3.0, ge=0.0, description="Weight: tỷ lệ sử dụng phòng tối ưu")
    weight_preserve_existing: float = Field(6.0, ge=0.0, description="Weight: giữ nguyên lịch cũ")

    # Optional advanced constraints
    paired_class_ids: Optional[List[List[UUID]]] = Field(
        None,
        description="Cặp lớp cần cùng buổi, VD: [[class_id_1, class_id_2], ...]"
    )

    # Per-class time preference (overrides auto-infer from preferred_slots)
    class_preferences: Optional[List[GAClassPreference]] = Field(
        None,
        description="Buổi ưa thích cho từng lớp. Nếu không nhập, tự suy từ preferred_slots."
    )

    # Session distribution weight
    weight_session_distribution: float = Field(
        8.0, ge=0.0,
        description="Weight: phân bổ đều số buổi mỗi tuần"
    )

    @field_validator('end_date')
    @classmethod
    def validate_date_range(cls, v: date, info) -> date:
        start = info.data.get('start_date')
        if start and v < start:
            raise ValueError('end_date phải >= start_date')
        return v

    @field_validator('paired_class_ids')
    @classmethod
    def validate_paired_classes(cls, v):
        if v:
            for pair in v:
                if len(pair) != 2:
                    raise ValueError('Mỗi cặp paired_class_ids phải có đúng 2 class_id')
        return v


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class GASessionProposal(BaseModel):
    """Chi tiết một session đề xuất từ GA."""
    id: UUID
    class_id: UUID
    class_name: str
    teacher_id: UUID
    teacher_name: str
    room_id: Optional[UUID] = None
    room_name: Optional[str] = None
    session_date: date
    time_slots: List[int]
    start_time: time
    end_time: time
    lesson_topic: Optional[str] = None
    is_conflict: bool = False
    conflict_details: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class GAConflictInfo(BaseModel):
    """Thông tin xung đột trong kết quả GA."""
    conflict_type: str
    entity_id: Optional[UUID] = None
    entity_name: Optional[str] = None
    session_date: date
    time_slots: List[int]
    reason: str


class GARunResponse(BaseModel):
    """Response tóm tắt khi tạo/xem GA run."""
    run_id: UUID
    status: str
    best_fitness: Optional[float] = None
    hard_violations: Optional[int] = None
    soft_score: Optional[float] = None
    total_sessions: Optional[int] = None
    conflict_count: Optional[int] = None
    generations_run: Optional[int] = None
    start_date: date
    end_date: date
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class GARunDetailResponse(GARunResponse):
    """Response chi tiết bao gồm danh sách sessions và conflicts."""
    sessions: List[GASessionProposal] = []
    conflicts: List[GAConflictInfo] = []
    statistics: Dict[str, Any] = {}
    config: Dict[str, Any] = {}


class GAApplyResponse(BaseModel):
    """Response khi apply GA proposal."""
    success: bool
    created_count: int
    message: str
    applied_run_id: UUID


# ============================================================================
# TEACHER UNAVAILABILITY SCHEMAS
# ============================================================================

class TeacherUnavailabilityCreate(BaseModel):
    """Request tạo lịch bận giáo viên."""
    teacher_id: UUID
    unavailable_date: Optional[date] = Field(None, description="Ngày bận (bắt buộc nếu is_recurring=false)")
    time_slots: Optional[List[int]] = Field(None, description="Tiết bận (null = cả ngày)")
    reason: str = Field("", max_length=255)
    is_recurring: bool = Field(False, description="True = lặp hàng tuần")
    day_of_week: Optional[int] = Field(None, ge=0, le=6, description="0=Mon, 6=Sun (bắt buộc nếu is_recurring=true)")

    @field_validator('day_of_week')
    @classmethod
    def validate_recurring(cls, v, info):
        is_recurring = info.data.get('is_recurring', False)
        unavailable_date = info.data.get('unavailable_date')
        if is_recurring and v is None:
            raise ValueError('day_of_week bắt buộc khi is_recurring=true')
        if not is_recurring and unavailable_date is None:
            raise ValueError('unavailable_date bắt buộc khi is_recurring=false')
        return v


class TeacherUnavailabilityResponse(BaseModel):
    """Response lịch bận giáo viên."""
    id: UUID
    teacher_id: UUID
    unavailable_date: Optional[date] = None
    time_slots: Optional[List[int]] = None
    reason: Optional[str] = None
    is_recurring: bool
    day_of_week: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
