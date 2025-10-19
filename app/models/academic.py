from sqlalchemy import Column, String, Integer, Text, DECIMAL, Enum, Date
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from app.models.base import BaseModel

import enum

# Room Enums
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

# Course Enums
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

# Room Model
class Room(BaseModel):
    __tablename__ = "rooms"
    
    name = Column(String(100), nullable=False, unique=True)
    capacity = Column(Integer, nullable=False)
    location = Column(String(255))
    equipment = Column(JSONB, default=list)  # [{"name": "projector", "quantity": 1}]
    room_type = Column(Enum(RoomType, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='room_type'), default=RoomType.CLASSROOM, nullable=False)
    status = Column(Enum(RoomStatus, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='room_status'), default=RoomStatus.AVAILABLE, nullable=False)
    notes = Column(Text)

# Course Model
class Course(BaseModel):
    __tablename__ = "courses"
    
    name = Column(String(255), nullable=False)
    description = Column(Text)
    level = Column(Enum(CourseLevel, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='course_level'), nullable=False)
    course_type = Column(Enum(CourseType, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='course_type'), default=CourseType.GENERAL_ENGLISH, nullable=False)
    
    # Duration and capacity
    duration_hours = Column(Integer, nullable=False)
    max_students = Column(Integer, default=25)
    min_students = Column(Integer, default=8)
    
    # Pricing
    fee_amount = Column(DECIMAL(10,2), nullable=False)
    currency = Column(String(3), default='VND')
    
    # Course content
    syllabus = Column(JSONB)  # Course structure
    learning_objectives = Column(ARRAY(Text()), default=list)
    prerequisites = Column(ARRAY(Text()), default=list)
    
    # Status
    status = Column(Enum(CourseStatus, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='course_status'), default=CourseStatus.ACTIVE, nullable=False)