from sqlalchemy import Column, String, Text, DECIMAL, Integer, Boolean, TIMESTAMP, ForeignKey, func, ARRAY, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.schema import CheckConstraint
from app.models.base import BaseModel
import enum

from app.models.academic import CourseLevel

class QuestionType(enum.Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    SHORT_ANSWER = "short_answer"
    ESSAY = "essay"
    SPEAKING = "speaking"
    LISTENING = "listening"

class SkillArea(enum.Enum):
    READING = "reading"
    WRITING = "writing"
    LISTENING = "listening"
    SPEAKING = "speaking"
    GRAMMAR = "grammar"
    VOCABULARY = "vocabulary"

class DifficultyLevel(enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class ContentStatus(enum.Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"
    NEEDS_REVIEW = "needs_review"

# --- TEST ENUMS ---
class TestType(enum.Enum):
    PLACEMENT = "placement"
    MIDTERM = "midterm"
    FINAL = "final"
    QUIZ = "quiz"

class TestStatus(enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"
    ARCHIVED = "archived"

class AttemptStatus(enum.Enum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    GRADED = "graded"
    CANCELLED = "cancelled"

# --- QUESTION BANK (Kho câu hỏi) ---
class QuestionBank(BaseModel):
    __tablename__ = "question_bank"
    
    title = Column(String(255), nullable=False)
    question_text = Column(Text, nullable=False)
    
    # Enums
    question_type = Column(Enum(QuestionType, native_enum=True, name='question_type'), nullable=False)
    skill_area = Column(Enum(SkillArea, native_enum=True, name='skill_area'), nullable=False)
    difficulty_level = Column(Enum(DifficultyLevel, native_enum=True, name='difficulty_level'), nullable=False)
    course_level = Column(Enum(CourseLevel, native_enum=True, name='course_level'), nullable=False)
    
    # Content
    options = Column(JSONB, default=list) # [{key: A, text: ..., is_correct: true}]
    correct_answer = Column(Text)
    rubric = Column(JSONB)
    audio_url = Column(Text)
    image_url = Column(Text)
    
    # Constraints
    time_limit_seconds = Column(Integer)
    points = Column(DECIMAL(4,2), default=1.00)
    tags = Column(ARRAY(String(100))) # ["grammar", "intermediate"]
    
    usage_count = Column(Integer, default=0)
    success_rate = Column(DECIMAL(5,2)) # [0, 100]
    status = Column(Enum(ContentStatus, native_enum=True, name='content_status'), default=ContentStatus.ACTIVE)
    
    # Audit/Review
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    reviewed_at = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        CheckConstraint('time_limit_seconds > 0', name='qb_time_limit_check'),
        CheckConstraint('points > 0', name='qb_points_check'),
        CheckConstraint('success_rate BETWEEN 0 AND 100', name='qb_success_rate_check'),
    )

# --- TESTS (Bài thi) ---
class Test(BaseModel):
    __tablename__ = "tests"
    
    title = Column(String(255), nullable=False)
    description = Column(Text)
    test_type = Column(Enum(TestType, native_enum=True, name='test_type'), nullable=False)
    
    # FKs
    class_id = Column(UUID(as_uuid=True), ForeignKey('classes.id', ondelete='SET NULL'), nullable=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey('courses.id', ondelete='RESTRICT'), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    
    # Constraints/Settings
    total_points = Column(DECIMAL(6,2), default=0)
    time_limit_minutes = Column(Integer)
    passing_score = Column(DECIMAL(5,2), default=60)
    max_attempts = Column(Integer, default=1)
    
    randomize_questions = Column(Boolean, default=False)
    show_results_immediately = Column(Boolean, default=True)
    
    start_time = Column(TIMESTAMP(timezone=True))
    end_time = Column(TIMESTAMP(timezone=True))
    instructions = Column(Text)
    status = Column(Enum(TestStatus, native_enum=True, name='test_status'), default=TestStatus.DRAFT)
    ai_grading_enabled = Column(Boolean, default=False)
    
    # Relationships
    questions = relationship("TestQuestion", back_populates="test")
    attempts = relationship("TestAttempt", back_populates="test")

    __table_args__ = (
        CheckConstraint('total_points >= 0', name='test_points_check'),
        CheckConstraint('time_limit_minutes > 0', name='test_time_limit_check'),
        CheckConstraint('passing_score BETWEEN 0 AND 100', name='test_passing_score_check'),
        CheckConstraint('max_attempts > 0', name='test_max_attempts_check'),
    )


# --- TEST QUESTIONS (Mối quan hệ N:N) ---
class TestQuestion(BaseModel):
    __tablename__ = "test_questions"
    
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id', ondelete='CASCADE'), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey('question_bank.id', ondelete='CASCADE'), nullable=False)
    order_number = Column(Integer, nullable=False)
    points = Column(DECIMAL(4,2), nullable=False, default=1.00)
    required = Column(Boolean, default=True)
    
    # Relationships
    test = relationship("Test", back_populates="questions")
    question = relationship("QuestionBank")

    __table_args__ = (
        CheckConstraint('order_number > 0', name='tq_order_check'),
        CheckConstraint('points > 0', name='tq_points_check'),
        UniqueConstraint('test_id', 'question_id', name='uq_test_question'),
    )


# --- TEST ATTEMPTS (Nỗ lực làm bài) ---
class TestAttempt(BaseModel):
    __tablename__ = "test_attempts"
    
    test_id = Column(UUID(as_uuid=True), ForeignKey('tests.id', ondelete='CASCADE'), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    attempt_number = Column(Integer, nullable=False, default=1)
    started_at = Column(TIMESTAMP(timezone=True), default=func.now())
    submitted_at = Column(TIMESTAMP(timezone=True))
    
    # Results
    time_taken_seconds = Column(Integer)
    total_score = Column(DECIMAL(6,2))
    percentage_score = Column(DECIMAL(5,2))
    passed = Column(Boolean)
    status = Column(Enum(AttemptStatus, native_enum=True, name='attempt_status'), default=AttemptStatus.IN_PROGRESS)
    
    # Feedback
    ai_feedback = Column(JSONB) 
    teacher_feedback = Column(Text)
    graded_by = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    graded_at = Column(TIMESTAMP(timezone=True))
    
    # Security/Audit
    ip_address = Column(String(45)) # INET type is usually handled as String in ORM
    user_agent = Column(Text)
    
    # Relationships
    test = relationship("Test", back_populates="attempts")
    student = relationship("User", backref="test_attempts")
    grader = relationship("User", foreign_keys=[graded_by])
    responses = relationship("TestResponse", back_populates="attempt")

    __table_args__ = (
        CheckConstraint('attempt_number > 0', name='ta_attempt_number_check'),
        CheckConstraint('time_taken_seconds >= 0', name='ta_time_check'),
        CheckConstraint('total_score >= 0', name='ta_total_score_check'),
        CheckConstraint('percentage_score BETWEEN 0 AND 100', name='ta_percentage_score_check'),
        UniqueConstraint('test_id', 'student_id', 'attempt_number', name='uq_test_student_attempt'),
    )


# --- TEST RESPONSES (Câu trả lời chi tiết) ---
class TestResponse(BaseModel):
    __tablename__ = "test_responses"
    
    attempt_id = Column(UUID(as_uuid=True), ForeignKey('test_attempts.id', ondelete='CASCADE'), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey('question_bank.id', ondelete='CASCADE'), nullable=False)
    
    response_text = Column(Text)
    response_data = Column(JSONB)
    audio_response_url = Column(Text)
    
    # Grading
    is_correct = Column(Boolean)
    points_earned = Column(DECIMAL(4,2), default=0)
    ai_score = Column(DECIMAL(4,2))
    ai_feedback = Column(Text)
    teacher_score = Column(DECIMAL(4,2))
    teacher_feedback = Column(Text)
    
    time_spent_seconds = Column(Integer)
    flagged_for_review = Column(Boolean, default=False)
    
    # Relationships
    attempt = relationship("TestAttempt", back_populates="responses")
    question = relationship("QuestionBank", backref="responses")

    __table_args__ = (
        CheckConstraint('points_earned >= 0', name='tr_points_earned_check'),
        CheckConstraint('ai_score >= 0', name='tr_ai_score_check'),
        CheckConstraint('teacher_score >= 0', name='tr_teacher_score_check'),
        CheckConstraint('time_spent_seconds >= 0', name='tr_time_spent_check'),
    )