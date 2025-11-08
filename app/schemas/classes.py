from pydantic import BaseModel, UUID4
from typing import Optional, Any
from datetime import date, datetime
from decimal import Decimal

class ClassBase(BaseModel):
    name: str
    course_id: UUID4
    teacher_id: UUID4
    substitute_teacher_id: Optional[UUID4]
    room_id: Optional[UUID4]
    start_date: date
    end_date: date
    schedule: Any
    max_students: int
    current_students: int
    fee_amount: Decimal
    sessions_per_week: int
    status: str
    notes: Optional[str]

class ClassResponse(ClassBase):
    id: UUID4
    created_at: datetime
    updated_at: Optional[datetime]
    deleted_at: Optional[datetime]
    created_by: Optional[UUID4]
    updated_by: Optional[UUID4]

    # thêm các tên được yêu cầu
    course_name: Optional[str]
    teacher_name: Optional[str]
    substitute_teacher_name: Optional[str]
    room_name: Optional[str]

    model_config = {
        "from_attributes": True
    }