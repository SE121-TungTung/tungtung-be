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

# File: app/models/test.py
import enum
# Giả định SkillArea đã được import từ cùng module hoặc module khác
# from .somewhere import SkillArea 

class QuestionType(enum.Enum):
    """Các dạng câu hỏi THỰC TẾ trong IELTS"""
    # === READING & LISTENING (dùng chung) ===
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE_NOT_GIVEN = "true_false_not_given"
    YES_NO_NOT_GIVEN = "yes_no_not_given"
    MATCHING_HEADINGS = "matching_headings"
    MATCHING_INFORMATION = "matching_information"
    MATCHING_FEATURES = "matching_features"
    SENTENCE_COMPLETION = "sentence_completion"
    SUMMARY_COMPLETION = "summary_completion"
    NOTE_COMPLETION = "note_completion"
    SHORT_ANSWER = "short_answer"
    DIAGRAM_LABELING = "diagram_labeling"
    
    # === WRITING ===
    WRITING_TASK_1 = "writing_task_1"
    WRITING_TASK_2 = "writing_task_2"
    
    # === SPEAKING ===
    SPEAKING_PART_1 = "speaking_part_1"
    SPEAKING_PART_2 = "speaking_part_2"
    SPEAKING_PART_3 = "speaking_part_3"
    
    @staticmethod
    def get_by_skill(skill_area: 'SkillArea') -> list['QuestionType']:
        """Trả về list QuestionType theo skill area"""
        mapping = {
            SkillArea.READING: [
                QuestionType.MULTIPLE_CHOICE,
                QuestionType.TRUE_FALSE_NOT_GIVEN,
                QuestionType.YES_NO_NOT_GIVEN,
                QuestionType.MATCHING_HEADINGS,
                QuestionType.MATCHING_INFORMATION,
                QuestionType.MATCHING_FEATURES,
                QuestionType.SENTENCE_COMPLETION,
                QuestionType.SUMMARY_COMPLETION,
                QuestionType.NOTE_COMPLETION,
                QuestionType.SHORT_ANSWER,
                QuestionType.DIAGRAM_LABELING,
            ],
            SkillArea.LISTENING: [
                QuestionType.MULTIPLE_CHOICE,
                QuestionType.SENTENCE_COMPLETION,
                QuestionType.SUMMARY_COMPLETION,
                QuestionType.NOTE_COMPLETION,
                QuestionType.SHORT_ANSWER,
                QuestionType.DIAGRAM_LABELING,
                QuestionType.MATCHING_FEATURES,
            ],
            SkillArea.WRITING: [
                QuestionType.WRITING_TASK_1,
                QuestionType.WRITING_TASK_2,
            ],
            SkillArea.SPEAKING: [
                QuestionType.SPEAKING_PART_1,
                QuestionType.SPEAKING_PART_2,
                QuestionType.SPEAKING_PART_3,
            ],
        }
        return mapping.get(skill_area, [])
    
    @staticmethod
    def get_metadata(question_type: 'QuestionType') -> dict:
        """Trả về metadata cho FE render"""
        metadata = {
            # === READING & LISTENING ===
            QuestionType.MULTIPLE_CHOICE: {
                "label": "Multiple Choice",
                "description": "Choose the correct letter.",
                "allows_multiple": True,  # Có thể "Choose TWO letters"
                "requires_options": True,
                "auto_gradable": True,
            },
            QuestionType.TRUE_FALSE_NOT_GIVEN: {
                "label": "True / False / Not Given",
                "description": "Identify if the statement agrees with the information.",
                "allows_multiple": False,
                "requires_options": False, # Options cố định [True, False, Not Given]
                "auto_gradable": True,
            },
            QuestionType.YES_NO_NOT_GIVEN: {
                "label": "Yes / No / Not Given",
                "description": "Identify if the statement agrees with the views of the writer.",
                "allows_multiple": False,
                "requires_options": False, # Options cố định [Yes, No, Not Given]
                "auto_gradable": True,
            },
            QuestionType.MATCHING_HEADINGS: {
                "label": "Matching Headings",
                "description": "Choose the correct heading for each paragraph.",
                "allows_multiple": False,
                "requires_options": True, # List of headings (i, ii, iii...)
                "auto_gradable": True,
            },
            QuestionType.MATCHING_INFORMATION: {
                "label": "Matching Information",
                "description": "Which paragraph contains the following information?",
                "allows_multiple": False, # Một câu hỏi chỉ map vào 1 đoạn (dù 1 đoạn có thể dùng nhiều lần)
                "requires_options": True, # List of paragraphs (A, B, C...)
                "auto_gradable": True,
            },
            QuestionType.MATCHING_FEATURES: {
                "label": "Matching Features",
                "description": "Match items with a list of options (e.g., researchers, dates).",
                "allows_multiple": False,
                "requires_options": True, # List of features/names box
                "auto_gradable": True,
            },
            QuestionType.SENTENCE_COMPLETION: {
                "label": "Sentence Completion",
                "description": "Complete the sentences using words from the text.",
                "allows_multiple": False,
                "requires_options": False,
                "auto_gradable": False, # Text input cần fuzzy match/normalization
                "word_limit_required": True,
            },
            QuestionType.SUMMARY_COMPLETION: {
                "label": "Summary Completion",
                "description": "Complete the summary.",
                "allows_multiple": False,
                # Summary có 2 dạng: Điền từ (No options) hoặc Chọn từ box (Has options)
                # Logic FE cần check field options có data không để render input text hay dropdown/drag-drop
                "requires_options": False, 
                "auto_gradable": False, 
                "word_limit_required": True,
            },
            QuestionType.NOTE_COMPLETION: {
                "label": "Note/Table/Flow-chart Completion",
                "description": "Complete the notes/table/flow-chart.",
                "allows_multiple": False,
                "requires_options": False,
                "auto_gradable": False,
                "word_limit_required": True,
            },
            QuestionType.SHORT_ANSWER: {
                "label": "Short Answer",
                "description": "Answer the questions with words from the text.",
                "allows_multiple": False,
                "requires_options": False,
                "auto_gradable": False,
                "word_limit_required": True,
            },
            QuestionType.DIAGRAM_LABELING: {
                "label": "Diagram Labeling",
                "description": "Label the parts of the diagram.",
                "allows_multiple": False,
                "requires_options": False,
                "requires_image": True, # Bắt buộc phải có hình ảnh diagram
                "auto_gradable": False,
                "word_limit_required": True,
            },
            
            # === WRITING ===
            QuestionType.WRITING_TASK_1: {
                "label": "Writing Task 1",
                "description": "Describe graph/chart/process/map (min 150 words).",
                "allows_multiple": False,
                "requires_options": False,
                "auto_gradable": False,
                "requires_rubric": True,
                "requires_image": True, # Thường Task 1 phải có hình đề bài
                "min_words": 150,
            },
            QuestionType.WRITING_TASK_2: {
                "label": "Writing Task 2",
                "description": "Write an essay in response to a point of view/argument (min 250 words).",
                "allows_multiple": False,
                "requires_options": False,
                "auto_gradable": False,
                "requires_rubric": True,
                "min_words": 250,
            },
            
            # === SPEAKING ===
            QuestionType.SPEAKING_PART_1: {
                "label": "Speaking Part 1",
                "description": "Introduction & Interview (4-5 minutes).",
                "allows_multiple": False,
                "requires_options": False,
                "auto_gradable": False,
                "requires_rubric": True,
                "requires_audio_response": True, # Học sinh phải ghi âm
            },
            QuestionType.SPEAKING_PART_2: {
                "label": "Speaking Part 2",
                "description": "Individual Long Turn (Cue Card). 1 min preparation, 2 min talk.",
                "allows_multiple": False,
                "requires_options": False,
                "auto_gradable": False,
                "requires_rubric": True,
                "requires_audio_response": True,
                "has_preparation_time": True, # Metadata riêng cho Part 2 để FE hiện timer chuẩn bị
            },
            QuestionType.SPEAKING_PART_3: {
                "label": "Speaking Part 3",
                "description": "Two-way Discussion based on Part 2 topic (4-5 minutes).",
                "allows_multiple": False,
                "requires_options": False,
                "auto_gradable": False,
                "requires_rubric": True,
                "requires_audio_response": True,
            },
        }
        return metadata.get(question_type, {})
    
    @staticmethod
    def is_auto_gradable(question_type: 'QuestionType') -> bool:
        """Check if question type can be auto-graded"""
        metadata = QuestionType.get_metadata(question_type)
        return metadata.get("auto_gradable", False)
    
    @staticmethod
    def requires_rubric(question_type: 'QuestionType') -> bool:
        """Check if question type requires rubric scoring"""
        metadata = QuestionType.get_metadata(question_type)
        return metadata.get("requires_rubric", False)


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
        Enum(TestStatus, values_callable=lambda x: [e.value for e in x], native_enum=False, name="test_status"),
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
        Enum(TestType, values_callable=lambda x: [e.value for e in x], native_enum=False, name="test_type"),
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
        Enum(SkillArea, values_callable=lambda x: [e.value for e in x], native_enum=False, name="skill_area"),
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

    passage_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("content_passages.id"),
        nullable=True  # Vì Speaking Part 1 không cần passage
    )
    instructions = Column(Text)

    audio_url = Column(String)
    image_url = Column(String)

    min_questions = Column(Integer)
    max_questions = Column(Integer)

    test_section = relationship("TestSection", back_populates="parts")
    passage = relationship("ContentPassage", back_populates="section_parts")
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
        Enum(QuestionType, values_callable=lambda x: [e.value for e in x], native_enum=False, name="question_type"),
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
        Enum(QuestionType, values_callable=lambda x: [e.value for e in x], native_enum=False, name="question_type"),
        nullable=False
    )

    skill_area = Column(
        Enum(SkillArea, values_callable=lambda x: [e.value for e in x], native_enum=False, name="skill_area"),
        nullable=False
    )

    difficulty_level = Column(
        Enum(DifficultyLevel, values_callable=lambda x: [e.value for e in x], native_enum=False, name="difficulty_level")
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
        Enum(ContentStatus, values_callable=lambda x: [e.value for e in x], native_enum=False, name="content_status"),
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
    group_order_number = Column(Integer, nullable=False)
    points = Column(Numeric(4, 2), default=1, nullable=False)
    required = Column(Boolean, default=True, nullable=False)

    test = relationship("Test", back_populates="questions")
    question = relationship("QuestionBank", back_populates="test_questions")
    group = relationship("QuestionGroup", back_populates="test_questions")

    __table_args__ = (
        UniqueConstraint("test_id", "order_number"),
        UniqueConstraint("test_id", "question_id"),
        UniqueConstraint("group_id", "group_order_number"),
        CheckConstraint("group_order_number > 0"),
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
        Enum(AttemptStatus, values_callable=lambda x: [e.value for e in x], native_enum=False, name="attempt_status"),
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
        Index("idx_test_attempts_test_id_status", "test_id", "status"),
        Index("idx_test_attempts_student_id", "student_id"),
    )


class TestResponse(BaseModel):
    __tablename__ = "test_responses"

    attempt_id = Column(UUID(as_uuid=True), ForeignKey("test_attempts.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="CASCADE"), nullable=False)

    response_text = Column(Text)
    response_data = Column(JSONB)
    audio_response_url = Column(String)
    
    auto_graded = Column(Boolean, default=True, nullable=False)

    # AUTO grading (Reading/Listening)
    is_correct = Column(Boolean)
    points_earned = Column(Numeric(4, 2), default=0)
    
    # MANUAL grading (Writing/Speaking)
    rubric_scores = Column(JSONB)  # {"task_achievement": 7, "coherence": 6.5, ...}
    band_score = Column(Numeric(3, 1))     # Band score (0-9, step 0.5)

    # AI grading (for manual gradable)
    ai_points_earned = Column(Numeric(4, 2), default=0)
    ai_band_score = Column(Numeric(3, 1))
    ai_rubric_scores = Column(JSONB)
    ai_feedback = Column(Text)

    # TEACHER OVERRIDE (for manual gradable)
    teacher_points_earned = Column(Numeric(4, 2), default=0)
    teacher_band_score = Column(Numeric(3, 1))
    teacher_rubric_scores = Column(JSONB)
    teacher_feedback = Column(Text)

    time_spent_seconds = Column(Integer)
    flagged_for_review = Column(Boolean, default=False, nullable=False)

    attempt = relationship("TestAttempt", back_populates="responses")
    question = relationship("QuestionBank", back_populates="responses")

    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id"),
        CheckConstraint("points_earned >= 0"),
        CheckConstraint("band_score IS NULL OR (band_score >= 0 AND band_score <= 9)"),
        CheckConstraint("ai_band_score IS NULL OR (ai_band_score >= 0 AND ai_band_score <= 9)"),
        CheckConstraint("teacher_band_score IS NULL OR (teacher_band_score >= 0 AND teacher_band_score <= 9)"),
        Index("idx_test_responses_attempt_id", "attempt_id"),
    )

class ContentPassage(BaseModel):
    """Lưu reading passage, listening audio script, context chung"""
    __tablename__ = "content_passages"
    
    title = Column(String(255), nullable=False)
    content_type = Column(
        Enum("reading_passage", "listening_audio", "speaking_cue_card", name="content_type"),
        nullable=False
    )
    
    # Content
    text_content = Column(Text)  # Reading passage text
    audio_url = Column(String)   # Listening audio URL
    image_url = Column(String)   # Diagram, map, chart...
    
    # Metadata
    topic = Column(String(100))  # VD: "Environment", "Technology"
    difficulty_level = Column(Enum(DifficultyLevel, values_callable=lambda x: [e.value for e in x], native_enum=False, name="difficulty_level"))
    word_count = Column(Integer)
    duration_seconds = Column(Integer)  # Cho listening
    
    # Reusability
    status = Column(
        Enum(ContentStatus, values_callable=lambda x: [e.value for e in x], native_enum=False, name="content_status"),
        default=ContentStatus.ACTIVE,
        nullable=False
    )
    usage_count = Column(Integer, default=0)
    
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    
    # Relationships
    section_parts = relationship("TestSectionPart", back_populates="passage")