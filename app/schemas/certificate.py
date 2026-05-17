from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

class CertificateBase(BaseModel):
    student_id: UUID4
    course_id: UUID4
    class_id: Optional[UUID4] = None
    certificate_code: str
    issue_date: date
    certificate_url: Optional[str] = None
    final_score: Optional[Decimal] = None
    attendance_rate: Optional[Decimal] = None

class CertificateCreate(CertificateBase):
    pass

class CertificateResponse(CertificateBase):
    id: UUID4
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }
