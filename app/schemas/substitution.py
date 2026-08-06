from pydantic import BaseModel, UUID4
from typing import Optional
from datetime import datetime, date, time
from app.models.substitution import SubstitutionStatus

class SubstitutionClassSessionResponse(BaseModel):
    id: UUID4
    session_date: date
    start_time: time
    end_time: time
    topic: Optional[str] = None
    class_id: UUID4
    class_name: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

class SubstitutionRequestCreate(BaseModel):
    class_session_id: UUID4
    target_substitute_id: Optional[UUID4] = None
    reason: str

class SubstitutionRequestResponse(BaseModel):
    id: UUID4
    class_session_id: UUID4
    requesting_teacher_id: UUID4
    target_substitute_id: Optional[UUID4] = None
    reason: str
    status: SubstitutionStatus
    admin_approval_required: bool
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[UUID4] = None
    admin_note: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Extra fields for frontend
    class_session: Optional[SubstitutionClassSessionResponse] = None
    requesting_teacher_name: Optional[str] = None
    target_substitute_name: Optional[str] = None

    model_config = {
        "from_attributes": True
    }
