from sqlalchemy import Column, String, Integer, SmallInteger,Text, DECIMAL, Enum, Date, TIMESTAMP, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.schema import UniqueConstraint

# Giả định: Bạn đã import BaseModel từ app.models.base
from app.models.base import BaseModel 
import enum

# --- ENUMERATIONS (Giữ nguyên) ---

class RoomType(enum.Enum):
    CLASSROOM = "classroom"
    COMPUTER_LAB = "computer_lab"
    MEETING_ROOM = "meeting_room"
    AUDITORIUM = "auditorium"
    LIBRARY = "library"

class RoomStatus(enum.Enum):
    AVAILABLE = "available"
    MAINTENANCE = "maintenance"
    UNAVAILABLE = "unavailable"
    RESERVED = "reserved"

class CourseLevel(enum.Enum):
    BEGINNER = "beginner"
    ELEMENTARY = "elementary"
    INTERMEDIATE = "intermediate"
    UPPER_INTERMEDIATE = "upper_intermediate"
    ADVANCED = "advanced"
    PROFICIENCY = "proficiency"

class CourseType(enum.Enum):
    GENERAL_ENGLISH = "general_english"
    IELTS = "ielts"
    TOEIC = "toeic"
    TOEFL = "toefl"
    BUSINESS = "business"
    CONVERSATION = "conversation"
    GRAMMAR = "grammar"
    WRITING = "writing"

class CourseStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"

class ClassStatus(enum.Enum):
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"

class PaymentStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    PARTIAL = "partial"
    REFUNDED = "refunded"
    OVERDUE = "overdue"

class EnrollmentStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DROPPED = "dropped"
    SUSPENDED = "suspended"
    TRANSFERRED = "transferred"

# --- MODELS ---

# Room Model (Đã sửa ENUM sang Native)
class Room(BaseModel):
    __tablename__ = "rooms"
    
    name = Column(String(100), nullable=False, unique=True)
    capacity = Column(Integer, nullable=False)
    location = Column(String(255))
    equipment = Column(JSONB, default=list)
    room_type = Column(Enum(RoomType, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=True, name='room_type'), default=RoomType.CLASSROOM, nullable=False)
    status = Column(Enum(RoomStatus, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=True, name='room_status'), default=RoomStatus.AVAILABLE, nullable=False)
    notes = Column(Text)

# Course Model (Đã sửa ENUM sang Native)
class Course(BaseModel):
    __tablename__ = "courses"
    
    name = Column(String(255), nullable=False)
    description = Column(Text)
    level = Column(Enum(CourseLevel, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=True, name='course_level'), nullable=False)
    course_type = Column(Enum(CourseType, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=True, name='course_type'), default=CourseType.GENERAL_ENGLISH, nullable=False)
    
    duration_hours = Column(Integer, nullable=False)
    max_students = Column(Integer, default=25)
    min_students = Column(Integer, default=8)
    
    fee_amount = Column(DECIMAL(10,2), nullable=False)
    currency = Column(String(3), default='VND')
    
    syllabus = Column(JSONB, nullable=False, default={}) 
    learning_objectives = Column(ARRAY(Text()), default=list)
    prerequisites = Column(ARRAY(Text()), default=list)
    
    status = Column(Enum(CourseStatus, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=True, name='course_status'), default=CourseStatus.ACTIVE, nullable=False)
    
# Class Model
class Class(BaseModel):
    __tablename__ = "classes"
    
    name = Column(String(255), nullable=False)
    
    # FIX UUID TYPE
    course_id = Column(UUID(as_uuid=True), ForeignKey('courses.id', ondelete='RESTRICT'), nullable=False)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='RESTRICT'), nullable=False)
    substitute_teacher_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    room_id = Column(UUID(as_uuid=True), ForeignKey('rooms.id', ondelete='SET NULL'), nullable=True)
    
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    schedule = Column(JSONB, nullable=False, default=list)
    
    max_students = Column(Integer, default=25, nullable=False)
    current_students = Column(Integer, default=0, nullable=False)
    
    fee_amount = Column(DECIMAL(10, 2), nullable=False)

    sessions_per_week = Column(SmallInteger, default=2, nullable=False)
    
    # FIX LOGIC: Default là SCHEDULED theo SQL gốc
    status = Column(Enum(ClassStatus, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=True, name='class_status'), default=ClassStatus.SCHEDULED, nullable=False) 
    
    notes = Column(Text, nullable=True)
    
    # created_by, updated_by, deleted_at được kế thừa và không định nghĩa lại ở đây.
    
    # Constraints
    __table_args__ = (
        CheckConstraint('current_students >= 0', name='classes_current_students_check'),
        CheckConstraint('fee_amount >= 0', name='classes_fee_amount_check'),
        CheckConstraint('max_students > 0', name='classes_max_students_check'),
        CheckConstraint('start_date <= end_date', name='classes_date_range_check'),
    )
    
    # Relationships
    course = relationship("Course", foreign_keys=[course_id])
    teacher = relationship("User", foreign_keys=[teacher_id], backref="classes_taught")
    substitute_teacher = relationship("User", foreign_keys=[substitute_teacher_id])
    room = relationship("Room")
    enrollments = relationship("ClassEnrollment", back_populates="enrollment_class")

# Class Enrollment Model
class ClassEnrollment(BaseModel):
    __tablename__ = "class_enrollments"
    
    # FIX UUID TYPE
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    enrollment_date = Column(TIMESTAMP(timezone=True), default=func.now())
    fee_paid = Column(DECIMAL(10,2), default=0)
    
    # Sửa ENUM sang Native
    payment_status = Column(Enum(PaymentStatus, values_callable=lambda obj: [e.value for e in obj],
                                 name='payment_status', native_enum=True), 
                            default=PaymentStatus.PENDING)
    status = Column(Enum(EnrollmentStatus, values_callable=lambda obj: [e.value for e in obj],
                         name='enrollment_status', native_enum=True), 
                    default=EnrollmentStatus.ACTIVE)

    completion_date = Column(TIMESTAMP(timezone=True))
    final_grade = Column(DECIMAL(3,2), nullable=True)
    attendance_rate = Column(DECIMAL(5,2), default=0)
    notes = Column(Text)

    # Thêm ràng buộc duy nhất (Unique Constraint) và Check Constraint
    __table_args__ = (
        UniqueConstraint('class_id', 'student_id', name='uq_class_student_enrollment'),
        CheckConstraint('fee_paid >= 0', name='class_enrollments_fee_paid_check'),
        CheckConstraint('final_grade IS NULL OR final_grade BETWEEN 0 AND 10', name='class_enrollments_final_grade_check'),
        CheckConstraint('attendance_rate BETWEEN 0 AND 100', name='class_enrollments_attendance_rate_check'),
    )

    # Relationships
    enrollment_class = relationship("Class", back_populates="enrollments")
    student = relationship("User", foreign_keys=[student_id], backref="class_enrollments")