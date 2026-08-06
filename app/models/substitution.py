from sqlalchemy import Column, String, Text, Enum, ForeignKey, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import BaseModel
import enum

class SubstitutionStatus(enum.Enum):
    PENDING = "PENDING" # Đang chờ substitute teacher confirm
    ACCEPTED = "ACCEPTED" # Substitute teacher đồng ý, chuyển sang chờ admin duyệt
    DECLINED = "DECLINED" # Substitute teacher từ chối
    APPROVED = "APPROVED" # Admin đã duyệt (hoàn tất)
    REJECTED = "REJECTED" # Admin từ chối
    CANCELLED = "CANCELLED" # GV xin nghỉ hủy yêu cầu

class SubstitutionRequest(BaseModel):
    __tablename__ = "substitution_requests"
    
    class_session_id = Column(UUID(as_uuid=True), ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=False)
    requesting_teacher_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    target_substitute_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True) # Có thể null nếu request open
    
    reason = Column(Text, nullable=False)
    status = Column(Enum(SubstitutionStatus, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name="substitution_status"), default=SubstitutionStatus.PENDING, nullable=False)
    
    admin_approval_required = Column(Boolean, default=True) # Theo spec, admin duyệt

    # Audit fields for state changes
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admin_note = Column(Text, nullable=True)

    # Relationships
    session = relationship("ClassSession")
    requesting_teacher = relationship("User", foreign_keys=[requesting_teacher_id])
    target_substitute = relationship("User", foreign_keys=[target_substitute_id])
    resolver = relationship("User", foreign_keys=[resolved_by])

    @property
    def requesting_teacher_name(self) -> str:
        return self.requesting_teacher.full_name if self.requesting_teacher else ""

    @property
    def target_substitute_name(self) -> str:
        return self.target_substitute.full_name if self.target_substitute else ""

    @property
    def class_session(self):
        return self.session

