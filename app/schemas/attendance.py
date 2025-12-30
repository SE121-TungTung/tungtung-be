from enum import Enum
from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from app.models.session_attendance import AttendanceStatus

class AttendanceUpdateItem(BaseModel):
    student_id: UUID
    status: AttendanceStatus
    notes: Optional[str] = None
    late_minutes: int = 0
    check_in_time: Optional[datetime] = None

class BatchAttendanceRequest(BaseModel):
    items: List[AttendanceUpdateItem]

class AttendanceResponseItem(BaseModel):
    student_id: UUID
    student_name: str
    student_code: Optional[str] = None
    avatar_url: Optional[str] = None
    status: AttendanceStatus
    late_minutes: int = 0
    notes: Optional[str] = None
    check_in_time: Optional[datetime] = None

    class Config:
        from_attributes = True

class StudentCheckInRequest(BaseModel):
    session_id: UUID

class StudentCheckInResponse(BaseModel):
    success: bool
    status: AttendanceStatus
    check_in_time: datetime
    late_minutes: int
    message: str