from sqlalchemy import UUID, ForeignKey
from sqlalchemy import Column, String, Text, Integer, Enum, CheckConstraint, UniqueConstraint
from app.models.base import BaseModel
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
import enum

class SkillArea(enum.Enum):
    LISTENING = "listening"
    READING = "reading"
    WRITING = "writing"
    SPEAKING = "speaking"
    GRAMMAR = "grammar"
    VOCABULARY = "vocabulary"

class ExamType(BaseModel):
    __tablename__ = "exam_types"

    code = Column(String(50), unique=True, nullable=False)  # 'IELTS', 'TOEIC'
    name = Column(String(255), nullable=False)
    description = Column(Text)

    structures = relationship("ExamStructure", back_populates="exam_type")


class ExamStructure(BaseModel):
    __tablename__ = "exam_structures"

    exam_type_id = Column(UUID(as_uuid=True), ForeignKey("exam_types.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    version = Column(Integer, default=1, nullable=False)

    exam_type = relationship("ExamType", back_populates="structures")
    sections = relationship("ExamStructureSection", back_populates="structure", cascade="all, delete-orphan")


class ExamStructureSection(BaseModel):
    __tablename__ = "exam_structure_sections"

    structure_id = Column(UUID(as_uuid=True), ForeignKey("exam_structures.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)  # Listening, Reading...
    skill_area = Column(
        Enum(SkillArea, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name="skill_area")
    )
    order_number = Column(Integer, nullable=False)
    time_limit_minutes = Column(Integer)  # optional override

    structure = relationship("ExamStructure", back_populates="sections")
    parts = relationship("ExamStructurePart", back_populates="section", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('structure_id', 'order_number', name='uq_structure_section_order'),
        CheckConstraint('order_number > 0', name='check_structure_section_order_positive'),
    )


class ExamStructurePart(BaseModel):
    __tablename__ = "exam_structure_parts"

    section_id = Column(UUID(as_uuid=True), ForeignKey("exam_structure_sections.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)  # e.g., Listening Part 1
    description = Column(Text)
    order_number = Column(Integer, nullable=False)
    min_questions = Column(Integer, nullable=True)
    max_questions = Column(Integer, nullable=True)
    # Accept array of allowed question types (store as JSONB or text[]). Here use JSONB for flexibility.
    question_type = Column(JSONB, nullable=True)

    section = relationship("ExamStructureSection", back_populates="parts")

    __table_args__ = (
        UniqueConstraint('section_id', 'order_number', name='uq_structure_part_order'),
        CheckConstraint('order_number > 0', name='check_structure_part_order_positive'),
    )