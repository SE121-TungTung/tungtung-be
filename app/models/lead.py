from sqlalchemy import Column, String, Text, Enum
from app.models.base import BaseModel
import enum

class LeadStatus(enum.Enum):
    NEW = "new"
    CONTACTED = "contacted"
    CONVERTED = "converted"
    LOST = "lost"

class Lead(BaseModel):
    __tablename__ = "lead_contacts"
    
    full_name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(20), index=True)
    
    guest_session_id = Column(String(255), index=True)
    source = Column(String(255), default="dual_hook") # e.g. "dual_hook_exam"
    
    status = Column(Enum(LeadStatus, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='lead_status'), default=LeadStatus.NEW, nullable=False)
    
    target_band = Column(String(50))
    notes = Column(Text)
