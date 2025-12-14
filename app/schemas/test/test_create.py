from typing import List, Optional, Any
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from app.models.test import TestType, QuestionType, DifficultyLevel, SkillArea

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

class TestSectionPartCreate(BaseModel):
    structure_part_id: Optional[UUID]  # Link to ExamStructurePart if applicable
    name: str
    order_number: int
    min_questions: Optional[int] = None
    max_questions: Optional[int] = None
    audio_url: Optional[str] = None
    image_url: Optional[str] = None
    instructions: Optional[str] = None

    questions: List[QuestionCreate]

class TestSectionCreate(BaseModel):
    structure_section_id: Optional[UUID]  # Link to ExamStructureSection if applicable
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
    exam_type_id: Optional[UUID]  # Link to ExamType for predefined
    structure_id: Optional[UUID]  # Link to ExamStructure for predefined

    sections: List[TestSectionCreate]