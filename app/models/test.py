from sqlalchemy import (
    Column, String, Text, Integer, Enum, CheckConstraint,
    UniqueConstraint, ForeignKey, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime, Numeric, Boolean
from app.models.base import BaseModel
import enum


# =========================
# ENUMS
# =========================

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


# =========================
# TEST CORE
# =========================

class Test(BaseModel):
    __tablename__ = "tests"

    title = Column(String(255), nullable=False)
    description = Column(Text)
    instructions = Column(Text)

    total_points = Column(Numeric(6, 2), default=0, nullable=False)
    time_limit_minutes = Column(Integer)
    passing_score = Column(Numeric(5, 2), default=60, nullable=False)
    max_attempts = Column(Integer, default=1, nullable=False)

    randomize_questions = Column(Boolean, default=False, nullable=False)
    show_results_immediately = Column(Boolean, default=True, nullable=False)

    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))

    status = Column(
        Enum(TestStatus, values_callable=lambda x: [e.value for e in x], name="test_status"),
        default=TestStatus.DRAFT,
        nullable=False
    )

    ai_grading_enabled = Column(Boolean, default=False, nullable=False)

    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="SET NULL"))
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="RESTRICT"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    exam_type_id = Column(UUID(as_uuid=True), ForeignKey("exam_types.id"))
    structure_id = Column(UUID(as_uuid=True), ForeignKey("exam_structures.id"))

    test_type = Column(
        Enum(TestType, values_callable=lambda x: [e.value for e in x], name="test_type"),
        nullable=True
    )

    sections = relationship("TestSection", back_populates="test", cascade="all, delete-orphan")
    questions = relationship("TestQuestion", back_populates="test", cascade="all, delete-orphan")
    attempts = relationship("TestAttempt", back_populates="test", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("total_points >= 0"),
        CheckConstraint("max_attempts > 0"),
    )


# =========================
# STRUCTURE
# =========================

class TestSection(BaseModel):
    __tablename__ = "test_sections"

    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    structure_section_id = Column(UUID(as_uuid=True), ForeignKey("exam_structure_sections.id"))

    name = Column(String(255), nullable=False)
    skill_area = Column(
        Enum(SkillArea, values_callable=lambda x: [e.value for e in x], name="skill_area"),
        nullable=False
    )

    order_number = Column(Integer, nullable=False)
    time_limit_minutes = Column(Integer)
    instructions = Column(Text)

    test = relationship("Test", back_populates="sections")
    parts = relationship("TestSectionPart", back_populates="test_section", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("test_id", "order_number"),
        CheckConstraint("order_number > 0"),
    )


class TestSectionPart(BaseModel):
    __tablename__ = "test_section_parts"

    test_section_id = Column(UUID(as_uuid=True), ForeignKey("test_sections.id", ondelete="CASCADE"), nullable=False)
    structure_part_id = Column(UUID(as_uuid=True), ForeignKey("exam_structure_parts.id"))

    name = Column(String(255), nullable=False)
    order_number = Column(Integer, nullable=False)

    content = Column(Text)
    instructions = Column(Text)

    audio_url = Column(String)
    image_url = Column(String)

    min_questions = Column(Integer)
    max_questions = Column(Integer)

    test_section = relationship("TestSection", back_populates="parts")

    question_groups = relationship(
        "QuestionGroup",
        back_populates="part",
        cascade="all, delete-orphan",
        order_by="QuestionGroup.order_number"
    )


    __table_args__ = (
        UniqueConstraint("test_section_id", "order_number"),
        CheckConstraint("order_number > 0"),
    )


# =========================
# QUESTION GROUP
# =========================

class QuestionGroup(BaseModel):
    __tablename__ = "question_groups"

    part_id = Column(
        UUID(as_uuid=True),
        ForeignKey("test_section_parts.id", ondelete="CASCADE"),
        nullable=False
    )

    name = Column(String(255))
    instructions = Column(Text)
    image_url = Column(String)

    order_number = Column(Integer, nullable=False)

    question_type = Column(
        Enum(QuestionType, values_callable=lambda x: [e.value for e in x], name="question_type"),
        nullable=False
    )

    part = relationship("TestSectionPart", back_populates="question_groups")

    test_questions = relationship(
        "TestQuestion",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="TestQuestion.order_number"
    )

    __table_args__ = (
        UniqueConstraint("part_id", "order_number"),
        CheckConstraint("order_number > 0"),
    )


# =========================
# QUESTION BANK
# =========================

class QuestionBank(BaseModel):
    __tablename__ = "question_bank"

    title = Column(String(255), nullable=False)
    question_text = Column(Text, nullable=False)

    question_type = Column(
        Enum(QuestionType, values_callable=lambda x: [e.value for e in x], name="question_type"),
        nullable=False
    )

    skill_area = Column(
        Enum(SkillArea, values_callable=lambda x: [e.value for e in x], name="skill_area"),
        nullable=False
    )

    difficulty_level = Column(
        Enum(DifficultyLevel, values_callable=lambda x: [e.value for e in x], name="difficulty_level")
    )

    options = Column(JSONB)
    correct_answer = Column(Text)
    explanation = Column(Text)
    rubric = Column(JSONB)

    audio_url = Column(String)
    image_url = Column(String)

    points = Column(Numeric(4, 2), default=1, nullable=False)
    tags = Column(JSONB)

    usage_count = Column(Integer, default=0, nullable=False)
    success_rate = Column(Numeric(5, 2))

    status = Column(
        Enum(ContentStatus, values_callable=lambda x: [e.value for e in x], name="content_status"),
        default=ContentStatus.ACTIVE,
        nullable=False
    )

    extra_metadata = Column(JSONB)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at = Column(DateTime(timezone=True))

    test_questions = relationship("TestQuestion", back_populates="question")
    responses = relationship("TestResponse", back_populates="question")


# =========================
# TEST QUESTION (LINK)
# =========================

class TestQuestion(BaseModel):
    __tablename__ = "test_questions"

    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey("question_groups.id", ondelete="CASCADE"), nullable=False)

    order_number = Column(Integer, nullable=False)
    points = Column(Numeric(4, 2), default=1, nullable=False)
    required = Column(Boolean, default=True, nullable=False)

    test = relationship("Test", back_populates="questions")
    question = relationship("QuestionBank", back_populates="test_questions")
    group = relationship("QuestionGroup", back_populates="test_questions")

    __table_args__ = (
        UniqueConstraint("test_id", "order_number"),
        UniqueConstraint("test_id", "question_id"),
        CheckConstraint("order_number > 0"),
    )


# =========================
# ATTEMPT & RESPONSE
# =========================

class TestAttempt(BaseModel):
    __tablename__ = "test_attempts"

    test_id = Column(UUID(as_uuid=True), ForeignKey("tests.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    attempt_number = Column(Integer, default=1, nullable=False)
    started_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True))

    time_taken_seconds = Column(Integer)
    total_score = Column(Numeric(6, 2))
    percentage_score = Column(Numeric(5, 2))
    band_score = Column(Numeric(4, 2))
    passed = Column(Boolean)

    status = Column(
        Enum(AttemptStatus, values_callable=lambda x: [e.value for e in x], name="attempt_status"),
        default=AttemptStatus.IN_PROGRESS,
        nullable=False
    )

    ai_feedback = Column(JSONB)
    teacher_feedback = Column(Text)

    graded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    graded_at = Column(DateTime(timezone=True))

    ip_address = Column(INET)
    user_agent = Column(Text)

    test = relationship("Test", back_populates="attempts")
    responses = relationship("TestResponse", back_populates="attempt", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("test_id", "student_id", "attempt_number"),
        CheckConstraint("attempt_number > 0"),
    )


class TestResponse(BaseModel):
    __tablename__ = "test_responses"

    attempt_id = Column(UUID(as_uuid=True), ForeignKey("test_attempts.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False)

    response_text = Column(Text)
    response_data = Column(JSONB)
    audio_response_url = Column(String)

    is_correct = Column(Boolean)
    points_earned = Column(Numeric(4, 2), default=0, nullable=False)

    auto_graded = Column(Boolean, default=True, nullable=False)
    feedback = Column(Text)

    ai_score = Column(Numeric(4, 2))
    ai_feedback = Column(Text)

    teacher_score = Column(Numeric(4, 2))
    teacher_feedback = Column(Text)

    time_spent_seconds = Column(Integer)
    flagged_for_review = Column(Boolean, default=False, nullable=False)

    attempt = relationship("TestAttempt", back_populates="responses")
    question = relationship("QuestionBank", back_populates="responses")

    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id"),
        CheckConstraint("points_earned >= 0"),
    )
