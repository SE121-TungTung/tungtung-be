from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import date
from uuid import UUID

class PublicCourseResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    level: str
    course_type: str
    duration_hours: int
    fee_amount: float
    currency: str

    model_config = {
        "from_attributes": True
    }

class PublicClassResponse(BaseModel):
    id: UUID
    name: str
    course_id: UUID
    course_name: str
    course_level: str
    start_date: date
    end_date: date
    sessions_per_week: int
    is_online: bool
    fee_amount: float
    max_students: int
    current_students: int
    available_spots: int

    model_config = {
        "from_attributes": True
    }

class PublicLeadCreate(BaseModel):
    full_name: str = Field(..., max_length=200)
    email: EmailStr
    phone: str = Field(..., max_length=20)
    target_band: Optional[str] = Field(None, max_length=50)
    intent: Optional[str] = None
