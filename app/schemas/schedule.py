from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Union
from datetime import date, time, datetime
from uuid import UUID

# --- Time Slot Configuration (System-wide) ---
class TimeSlot(BaseModel):
    """Khung giờ tiết học cố định của hệ thống"""
    slot_number: int = Field(..., ge=1, le=10, description="Tiết thứ mấy trong ngày")
    start_time: time
    end_time: time
    
    class Config:
        json_schema_extra = {
            "example": {
                "slot_number": 1,
                "start_time": "08:00:00",
                "end_time": "09:30:00"
            }
        }

# --- Output Components ---
class SessionProposal(BaseModel):
    """Một buổi học được đề xuất"""
    class_id: UUID
    class_name: str
    teacher_id: UUID
    teacher_name: str
    room_id: UUID
    room_name: str
    session_date: date
    time_slots: List[int] = Field(..., description="Danh sách số tiết, VD: [1, 2]")
    start_time: time
    end_time: time
    lesson_topic: Optional[str] = None

class ConflictInfo(BaseModel):
    """Thông tin xung đột"""
    class_id: UUID
    class_name: str
    conflict_type: str  # "teacher_busy", "room_unavailable", "no_slots"
    session_date: date
    time_slots: List[int]
    reason: str
    suggestions: List[Dict[str, Any]] = Field(default_factory=list)

class ScheduleProposal(BaseModel):
    """Output: Proposal từ AI để admin review trước khi apply"""
    total_classes: int
    successful_sessions: int
    conflict_count: int
    
    sessions: List[SessionProposal]
    conflicts: List[ConflictInfo]
    
    statistics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Thống kê: phòng sử dụng, giờ peak, etc."
    )

# --- Input: Schedule Generation Request (UC MF.3) ---
class ScheduleGenerateRequest(BaseModel):
    """Input để AI tạo schedule cho classes"""
    start_date: date = Field(..., description="Ngày bắt đầu tạo lịch")
    end_date: date = Field(..., description="Ngày kết thúc tạo lịch")
    
    class_ids: Optional[List[UUID]] = Field(None, description="Danh sách class cần xếp lịch.")
    max_slots_per_session: Optional[int] = Field(None, ge=1, le=4, description="Giới hạn số tiết tối đa cho một buổi học")
    prefer_morning: bool = Field(True, description="Ưu tiên xếp buổi sáng")
    
    @validator('end_date')
    def validate_date_range(cls, v: date, values: Dict[str, Any]) -> date:
        if 'start_date' in values and v < values['start_date']:
            raise ValueError('end_date phải >= start_date')
        return v

# --- Manual CRUD Operations ---
class SessionCreate(BaseModel):
    """Tạo session thủ công (UC MF.3.1)"""
    class_id: UUID
    session_date: date
    time_slots: List[int] = Field(..., min_items=1, max_items=4)
    room_id: Optional[UUID] = Field(None, description="Nếu None, AI tự chọn phòng")
    teacher_id: Optional[UUID] = Field(None, description="Nếu None, dùng teacher của class")
    topic: Optional[str] = None
    notes: Optional[str] = None

class SessionUpdate(BaseModel):
    """Cập nhật session (UC MF.3.3)"""
    session_date: Optional[date] = None
    time_slots: Optional[List[int]] = None
    room_id: Optional[UUID] = None
    teacher_id: Optional[UUID] = None  # Substitute teacher
    topic: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None  # scheduled, cancelled, completed

class SessionResponse(BaseModel):
    """Response cho session"""
    id: UUID
    class_id: UUID
    class_name: str
    teacher_id: UUID
    teacher_name: str
    room_id: UUID
    room_name: str
    session_date: date
    start_time: time
    end_time: time
    time_slots: List[int]
    topic: Optional[str]
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class WeeklySession(BaseModel):
    session_id: UUID
    class_name: str
    teacher_name: str
    room_name: str
    day_of_week: str
    start_time: time
    end_time: time
    topic: Optional[str]

class WeeklySchedule(BaseModel):
    schedule: List[WeeklySession]

class ScheduleCopyRequest(BaseModel):
    """Copy schedule từ tuần/tháng trước (AF1)"""
    source_start_date: date
    source_end_date: date
    target_start_date: date
    class_ids: Optional[List[UUID]] = None

# END OF app/schemas/schedule.py