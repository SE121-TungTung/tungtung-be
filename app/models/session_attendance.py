from sqlalchemy import Column, Date, Time, Text, ForeignKey, TIMESTAMP, Boolean, Integer, String, Enum, CheckConstraint, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel
import enum

# SESSION ENUMS
class SessionStatus(enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"

# ATTENDANCE ENUMS
class AttendanceStatus(enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"

class ClassSession(BaseModel):
    __tablename__ = "class_sessions"
    
    # Foreign Keys
    class_id = Column(UUID(as_uuid=True), ForeignKey('classes.id', ondelete='CASCADE'), nullable=False)
    room_id = Column(UUID(as_uuid=True), ForeignKey('rooms.id', ondelete='SET NULL'), nullable=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    substitute_teacher_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    
    # Time and Topic
    session_date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    time_slots = Column(ARRAY(Integer), nullable=False)
    topic = Column(String(255))
    description = Column(Text)
    
    # Materials (JSONB and default=list for mutability)
    materials = Column(JSONB, default=list) # Default [] cho Array/List
    homework = Column(JSONB)
    
    # Status and Audit
    status = Column(Enum(SessionStatus, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=True, name='session_status'), default=SessionStatus.SCHEDULED)
    attendance_taken = Column(Boolean, default=False)
    notes = Column(Text)
    
    # Actual times
    actual_start_time = Column(TIMESTAMP(timezone=True))
    actual_end_time = Column(TIMESTAMP(timezone=True))
    
    # Relationships
    session_class = relationship("Class", backref="sessions")
    teacher = relationship("User", foreign_keys=[teacher_id])
    substitute_teacher = relationship("User", foreign_keys=[substitute_teacher_id])
    room = relationship("Room")
    attendance_records = relationship("AttendanceRecord", back_populates="session")

class AttendanceRecord(BaseModel):
    __tablename__ = "attendance_records"
    
    # Foreign Keys
    session_id = Column(UUID(as_uuid=True), ForeignKey('class_sessions.id', ondelete='CASCADE'), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    marked_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
    # Status
    status = Column(Enum(AttendanceStatus, values_callable=lambda obj: [e.value for e in obj],
        native_enum=True, name='attendance_status'), nullable=False)
    
    # Time and Details
    check_in_time = Column(TIMESTAMP(timezone=True))
    check_out_time = Column(TIMESTAMP(timezone=True))
    late_minutes = Column(Integer, default=0)
    notes = Column(Text)
    
    # Relationships
    session = relationship("ClassSession", back_populates="attendance_records")
    student = relationship("User", foreign_keys=[student_id], backref="attendance_logs")
    marker = relationship("User", foreign_keys=[marked_by])

    # Constraints (Check constraint cho late_minutes)
    __table_args__ = (
        CheckConstraint('late_minutes >= 0', name='attendance_late_minutes_check'),
    )