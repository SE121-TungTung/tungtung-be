from sqlalchemy import UUID, ForeignKey
from sqlalchemy import Column, String, Text, Integer, Enum, CheckConstraint, UniqueConstraint, Index
from app.models.base import BaseModel
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime, Numeric, Boolean
import enum

class QuestionType(enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    LISTENING = "listening"
    SPEAKING = "speaking"
    READING = "reading_comprehension"
    FILL_IN_BLANK = "fill_in_blank"
    MATCHING = "matching"
    ORDERING = "ordering"
    DRAG_AND_DROP = "drag_and_drop"

class SkillArea(enum.Enum):
    LISTENING = "listening"
    READING = "reading"
    WRITING = "writing"
    SPEAKING = "speaking"
    GRAMMAR = "grammar"
    VOCABULARY = "vocabulary"
    PRONUNCIATION = "pronunciation"

class DifficultyLevel(enum.Enum):
    VERY_EASY = "very_easy"
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    VERY_HARD = "very_hard"

class ContentStatus(enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    UNDER_REVIEW = "under_review"

class TestType(enum.Enum):
    QUIZ = "quiz"
    MIDTERM = "midterm"
    FINAL = "final"
    PLACEMENT = "placement"
    HOMEWORK = "homework"
    ASSESSMENT = "assessment"

class TestStatus(enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"

class AttemptStatus(enum.Enum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    GRADED = "graded"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

class Test(BaseModel):
    __tablename__ = "tests"

    title = Column(String(255), nullable=False)
    description = Column(Text)
    instructions = Column(Text)

    total_points = Column(Numeric(6,2), default=0, nullable=False)
    time_limit_minutes = Column(Integer)
    passing_score = Column(Numeric(5,2), default=60, nullable=False)
    max_attempts = Column(Integer, default=1, nullable=False)
    randomize_questions = Column(Boolean, default=False, nullable=False)
    show_results_immediately = Column(Boolean, default=True, nullable=False)
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    status = Column(
        Enum(TestStatus, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='test_status'),
        default=TestStatus.DRAFT, nullable=False
    )
    ai_grading_enabled = Column(Boolean, default=False, nullable=False)
    
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="SET NULL"), nullable=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Link to structure/template if this test follows a known structure (eg IELTS)
    exam_type_id = Column(UUID(as_uuid=True), ForeignKey("exam_types.id"), nullable=True)
    structure_id = Column(UUID(as_uuid=True), ForeignKey("exam_structures.id"), nullable=True)
    test_type = Column(
        Enum(TestType, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='test_type'),
        nullable=True, default=None
    )

    sections = relationship("TestSection", back_populates="test", cascade="all, delete-orphan")
    questions = relationship("TestQuestion", back_populates="test", cascade="all, delete-orphan")
    attempts = relationship("TestAttempt", back_populates="test", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint('total_points >= 0', name='check_tests_total_points_nonneg'),
        CheckConstraint('max_attempts > 0', name='check_tests_max_attempts_positive'),
    )


class TestSection(BaseModel):
    __tablename__ = "test_sections"

    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    structure_section_id = Column(UUID(as_uuid=True), ForeignKey("exam_structure_sections.id"), nullable=True)
    name = Column(String(255), nullable=False)
    skill_area = Column(
        Enum(SkillArea, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='skill_area'),
        nullable=False
    )
    order_number = Column(Integer, nullable=False)
    time_limit_minutes = Column(Integer)
    instructions = Column(Text)

    test = relationship("Test", back_populates="sections")
    parts = relationship("TestSectionPart", back_populates="test_section", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('test_id', 'order_number', name='uq_test_section_order'),
        CheckConstraint('order_number > 0', name='check_test_section_order_positive'),
    )


class TestSectionPart(BaseModel):
    __tablename__ = "test_section_parts"

    test_section_id = Column(UUID(as_uuid=True), ForeignKey("test_sections.id", ondelete="CASCADE"), nullable=False)
    structure_part_id = Column(UUID(as_uuid=True), ForeignKey("exam_structure_parts.id"), nullable=True)
    name = Column(String(255), nullable=False)
    order_number = Column(Integer, nullable=False)
    min_questions = Column(Integer)
    max_questions = Column(Integer)
    audio_url = Column(String, nullable=True)   # for Listening part
    image_url = Column(String, nullable=True)
    instructions = Column(Text)

    test_section = relationship("TestSection", back_populates="parts")
    questions = relationship("TestQuestion", back_populates="part", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('test_section_id', 'order_number', name='uq_test_section_part_order'),
        CheckConstraint('order_number > 0', name='check_test_section_part_order_positive'),
    )


class QuestionBank(BaseModel):
    __tablename__ = "question_bank"

    title = Column(String(255), nullable=False)
    question_text = Column(Text, nullable=False)
    question_type = Column(
        Enum(QuestionType, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='question_type'),
        nullable=False
    )
    skill_area = Column(
        Enum(SkillArea, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='skill_area'),
        nullable=False
    )
    difficulty_level = Column(
        Enum(DifficultyLevel, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='difficulty_level'),
        nullable=True
    )
    options = Column(JSONB, nullable=True)  # [{"key":"A","text":"...","is_correct":true}]
    correct_answer = Column(Text, nullable=True)
    rubric = Column(JSONB, nullable=True)
    audio_url = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    points = Column(Numeric(4,2), default=1.00, nullable=False)
    tags = Column(JSONB, nullable=True)  # store as array or json list
    usage_count = Column(Integer, default=0, nullable=False)
    success_rate = Column(Numeric(5,2), nullable=True)
    status = Column(
        Enum(ContentStatus, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='content_status'),
        default=ContentStatus.ACTIVE, nullable=False
    )
    extra_metadata = Column(JSONB, nullable=True)  # store source_pdf, page refs, multiple_answers_allowed, etc.

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True))

    test_questions = relationship("TestQuestion", back_populates="question", cascade="all, delete-orphan")
    responses = relationship("TestResponse", back_populates="question")


class TestQuestion(BaseModel):
    __tablename__ = "test_questions"

    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False)
    part_id = Column(UUID(as_uuid=True), ForeignKey("test_section_parts.id", ondelete="CASCADE"), nullable=True)
    order_number = Column(Integer, nullable=False)
    points = Column(Numeric(4,2), default=1.00, nullable=False)
    required = Column(Boolean, default=True, nullable=False)

    test = relationship("Test", back_populates="questions")
    question = relationship("QuestionBank", back_populates="test_questions")
    part = relationship("TestSectionPart", back_populates="questions")

    __table_args__ = (
        UniqueConstraint('test_id', 'question_id', name='uq_test_question_unique'),
        UniqueConstraint('test_id', 'order_number', name='uq_test_question_order'),
        CheckConstraint('order_number > 0', name='check_test_question_order_positive'),
    )


class TestAttempt(BaseModel):
    __tablename__ = "test_attempts"

    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    attempt_number = Column(Integer, default=1, nullable=False)
    started_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    time_taken_seconds = Column(Integer, nullable=True)
    total_score = Column(Numeric(6,2), nullable=True)
    percentage_score = Column(Numeric(5,2), nullable=True)
    passed = Column(Boolean, nullable=True)
    status = Column(
        Enum(AttemptStatus, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='attempt_status'),
        default=AttemptStatus.IN_PROGRESS, nullable=False
    )
    ai_feedback = Column(JSONB, nullable=True)
    teacher_feedback = Column(Text, nullable=True)
    graded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    graded_at = Column(DateTime(timezone=True), nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)

    test = relationship("Test", back_populates="attempts")
    student = relationship("User", foreign_keys=[student_id])
    responses = relationship("TestResponse", back_populates="attempt", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('test_id', 'student_id', 'attempt_number', name='uq_attempt_unique'),
        CheckConstraint('attempt_number > 0', name='check_attempt_number_positive'),
        CheckConstraint('(submitted_at IS NULL) OR (submitted_at >= started_at)', name='check_submission_time'),
    )


class TestResponse(BaseModel):
    __tablename__ = "test_responses"

    attempt_id = Column(UUID(as_uuid=True), ForeignKey("test_attempts.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False)

    response_text = Column(Text, nullable=True)
    response_data = Column(JSONB, nullable=True)
    audio_response_url = Column(String, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    points_earned = Column(Numeric(4,2), default=0, nullable=False)
    ai_score = Column(Numeric(4,2), nullable=True)
    ai_feedback = Column(Text, nullable=True)
    teacher_score = Column(Numeric(4,2), nullable=True)
    teacher_feedback = Column(Text, nullable=True)
    time_spent_seconds = Column(Integer, nullable=True)
    flagged_for_review = Column(Boolean, default=False, nullable=False)

    attempt = relationship("TestAttempt", back_populates="responses")
    question = relationship("QuestionBank", back_populates="responses")

    __table_args__ = (
        UniqueConstraint('attempt_id', 'question_id', name='uq_response_attempt_question'),
        CheckConstraint('points_earned >= 0', name='check_points_earned_nonneg'),
    )


# class ScoreConversion(BaseModel):
#     __tablename__ = "score_conversions"

#     exam_type_id = Column(UUID(as_uuid=True), ForeignKey("exam_types.id"), nullable=False)
#     section_name = Column(String(50), nullable=False)   # Listening / Reading / Overall etc.
#     raw_min = Column(Integer, nullable=False)
#     raw_max = Column(Integer, nullable=False)
#     band = Column(Numeric(3,1), nullable=False)

#     exam_type = relationship("ExamType")

#     __table_args__ = (
#         CheckConstraint('raw_min <= raw_max', name='check_scoreconv_min_le_max'),
#         UniqueConstraint('exam_type_id', 'section_name', 'raw_min', 'raw_max', name='uq_scoreconv_range'),
#     )