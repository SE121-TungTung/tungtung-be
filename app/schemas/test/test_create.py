from typing import List, Optional, Any
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from app.models.test import TestType, QuestionType, DifficultyLevel, SkillArea, TestStatus

class QuestionCreate(BaseModel):
    id: Optional[UUID] = None  # For existing question reuse

    title: str
    question_text: str
    question_type: QuestionType
    difficulty_level: Optional[DifficultyLevel] = DifficultyLevel.MEDIUM
    skill_area: SkillArea
    
    options: Optional[List[dict]] = None  # [{"key":"A","text":"...","is_correct":true}]
    correct_answer: Optional[str] = None
    rubric: Optional[dict] = None  # e.g., {"criteria": "...", "points": ...}

    audio_url: Optional[str] = None
    image_url: Optional[str] = None

    points: float = 1.0
    tags: Optional[List[str]] = None
    
    # Metadata: source, page, multiple answers allowed…
    extra_metadata: Optional[dict[str, Any]] = None

class QuestionGroupCreate(BaseModel):
    id: Optional[UUID] = None  # reuse group if needed

    name: str  # e.g. "Questions 1-5"
    order_number: int

    question_type: QuestionType  # TFNG, FILL_BLANK, MATCHING
    instructions: Optional[str] = None  # markdown
    image_url: Optional[str] = None

    min_questions: Optional[int] = None
    max_questions: Optional[int] = None

    questions: List[QuestionCreate]

class PassageCreate(BaseModel):
    """Schema for creating passage inline"""
    title: str
    content_type: str  # "reading_passage", "listening_audio", "speaking_cue_card"
    text_content: Optional[str] = None
    audio_url: Optional[str] = None
    image_url: Optional[str] = None
    topic: Optional[str] = None
    difficulty_level: Optional[str] = None
    word_count: Optional[int] = None
    duration_seconds: Optional[int] = None

class TestSectionPartCreate(BaseModel):
    structure_part_id: Optional[UUID] = None # Link to ExamStructurePart if applicable
    name: str
    order_number: int

     # Option 1: Link to existing passage
    passage_id: Optional[UUID] = None
    
    # Option 2: Create new passage inline
    passage: Optional[PassageCreate] = None

    min_questions: Optional[int] = None
    max_questions: Optional[int] = None
    audio_url: Optional[str] = None
    image_url: Optional[str] = None
    instructions: Optional[str] = None

    question_groups: List[QuestionGroupCreate]

class TestSectionCreate(BaseModel):
    structure_section_id: Optional[UUID] = None  # Link to ExamStructureSection if applicable
    name: str
    order_number: int
    skill_area: SkillArea
    time_limit_minutes: Optional[int] = None
    instructions: Optional[str] = None

    parts: List[TestSectionPartCreate]

class TestCreate(BaseModel):
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    
    time_limit_minutes: Optional[int] = None
    passing_score: Optional[float] = None
    max_attempts: Optional[int] = None
    randomize_questions: Optional[bool] = False
    show_results_immediately: Optional[bool] = False
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    ai_grading_enabled: Optional[bool] = False

    class_id: Optional[UUID] = None  # Link to class if applicable
    course_id: Optional[UUID] = None  # Link to course if applicable

    # Link to structure/template if this test follows a known structure (eg IELTS)
    test_type: Optional[TestType] = None
    exam_type_id: Optional[UUID] = None # Link to ExamType for predefined
    structure_id: Optional[UUID] = None  # Link to ExamStructure for predefined

    status: Optional[TestStatus] = TestStatus.DRAFT

    sections: List[TestSectionCreate]

class TestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None

    time_limit_minutes: Optional[int] = None
    passing_score: Optional[float] = None
    max_attempts: Optional[int] = None

    randomize_questions: Optional[bool] = None
    show_results_immediately: Optional[bool] = None
    ai_grading_enabled: Optional[bool] = None

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None