from typing import List, Optional
from pydantic import BaseModel, model_validator
from uuid import UUID
from datetime import datetime
from app.models.session_attendance import AttendanceStatus


# ============================================================
# EXISTING SCHEMAS (giữ nguyên / sửa nhẹ)
# ============================================================

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

    model_config = {
        "from_attributes": True
    }


# ============================================================
# SELF CHECK-IN (Sửa: hỗ trợ QR token)
# ============================================================

class StudentCheckInRequest(BaseModel):
    session_id: Optional[UUID] = None
    qr_token: Optional[str] = None

    @model_validator(mode="after")
    def validate_at_least_one(self):
        if not self.session_id and not self.qr_token:
            raise ValueError("Phải cung cấp ít nhất session_id hoặc qr_token")
        return self

class StudentCheckInResponse(BaseModel):
    success: bool
    status: AttendanceStatus
    check_in_time: Optional[datetime] = None
    late_minutes: int = 0
    message: str


# ============================================================
# NOTES UPDATE (sau tiết học)
# ============================================================

class AttendanceNoteUpdate(BaseModel):
    """Cập nhật ghi chú cho 1 học viên (chỉ notes, không đổi status)"""
    student_id: UUID
    notes: str

class BatchNoteUpdateRequest(BaseModel):
    items: List[AttendanceNoteUpdate]


# ============================================================
# QR CODE
# ============================================================

class QRTokenResponse(BaseModel):
    session_id: UUID
    qr_token: str
    expires_at: datetime


# ============================================================
# THỐNG KÊ & BÁO CÁO
# ============================================================

class StudentAttendanceStats(BaseModel):
    """Thống kê điểm danh theo từng học viên trong 1 lớp"""
    student_id: UUID
    student_name: str
    total_sessions: int
    present_count: int
    absent_count: int
    late_count: int
    excused_count: int
    attendance_rate: float            # (PRESENT+LATE) / (PRESENT+LATE+ABSENT) * 100
    is_certificate_eligible: bool     # rate >= threshold (EXCUSED tính là attended)

    model_config = {"from_attributes": True}

class ClassAttendanceStats(BaseModel):
    """Thống kê điểm danh tổng hợp cho 1 lớp"""
    class_id: UUID
    class_name: str
    total_sessions_held: int
    average_attendance_rate: float
    students_below_threshold: int
    total_students: int

    model_config = {"from_attributes": True}

class AbsentAlertItem(BaseModel):
    """Cảnh báo học viên vắng nhiều"""
    student_id: UUID
    student_name: str
    class_id: UUID
    class_name: str
    absent_count: int
    attendance_rate: float

    model_config = {"from_attributes": True}


# ============================================================
# CERTIFICATE ELIGIBILITY
# ============================================================

class CertificateEligibilityResponse(BaseModel):
    enrollment_id: UUID
    student_id: UUID
    student_name: str
    class_name: str
    attendance_rate: float          # Rate dùng cho certificate (EXCUSED = attended)
    min_rate_required: float
    is_eligible: bool

    model_config = {"from_attributes": True}


# ============================================================
# ATTENDANCE CONFIG
# ============================================================

class AttendanceConfigResponse(BaseModel):
    min_rate_percent: float
    grace_period_min: int
    early_checkin_min: int
    alert_absence_count: int

class AttendanceConfigUpdate(BaseModel):
    min_rate_percent: Optional[float] = None
    grace_period_min: Optional[int] = None
    early_checkin_min: Optional[int] = None
    alert_absence_count: Optional[int] = None