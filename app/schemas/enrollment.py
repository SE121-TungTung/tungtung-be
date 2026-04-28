from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Optional
from datetime import datetime
from decimal import Decimal


class ClassEnrollmentCreateAuto(BaseModel):
    student_id: UUID
    class_id: UUID


class ClassEnrollmentResponse(BaseModel):
    """Response schema cho ClassEnrollment, có thêm tên học sinh và tên lớp."""
    id: UUID
    class_id: UUID
    class_name: Optional[str] = None
    student_id: UUID
    student_name: Optional[str] = None
    enrollment_date: Optional[datetime] = None
    fee_paid: Optional[Decimal] = None
    payment_status: Optional[str] = None
    status: Optional[str] = None
    completion_date: Optional[datetime] = None
    final_grade: Optional[Decimal] = None
    attendance_rate: Optional[Decimal] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
