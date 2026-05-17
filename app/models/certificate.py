from sqlalchemy import Column, String, Text, ForeignKey, Date, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import BaseModel

class Certificate(BaseModel):
    __tablename__ = "certificates"

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="SET NULL"), nullable=True)
    
    certificate_code = Column(String(50), unique=True, nullable=False, index=True)
    issue_date = Column(Date, default=func.current_date(), nullable=False)
    
    certificate_url = Column(Text, nullable=True) # URL of the generated PDF
    final_score = Column(Numeric(5, 2), nullable=True)
    attendance_rate = Column(Numeric(5, 2), nullable=True)

    # Relationships
    student = relationship("User", foreign_keys=[student_id])
    course = relationship("Course", foreign_keys=[course_id])
    student_class = relationship("Class", foreign_keys=[class_id])
