from pydantic import BaseModel, UUID4
from typing import List, Optional, Any
from datetime import datetime

# ---------------------------
# Base / Student-facing schemas
# ---------------------------

class QuestionResponse(BaseModel):
    id: UUID4
    title: Optional[str] = None
    question_text: Optional[str] = None
    question_type: str
    difficulty_level: Optional[str] = None
    skill_area: Optional[str] = None
    options: Optional[Any] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    points: int
    tags: Optional[List[str]] = None
    # rename internal -> visible metadata for safety
    visible_metadata: Optional[Any] = None

    model_config = {
        "from_attributes": True
    }


class PartResponse(BaseModel):
    id: UUID4
    name: str
    order_number: int
    min_questions: Optional[int] = None
    max_questions: Optional[int] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    instructions: Optional[str] = None
    questions: List[QuestionResponse]

    model_config = {
        "from_attributes": True
    }


class SectionResponse(BaseModel):
    id: UUID4
    name: str
    order_number: int
    skill_area: Optional[str] = None
    time_limit_minutes: Optional[int] = None
    instructions: Optional[str] = None
    parts: List[PartResponse]

    model_config = {
        "from_attributes": True
    }


class TestResponse(BaseModel):
    id: UUID4
    title: str
    description: Optional[str]
    instructions: Optional[str]
    test_type: str
    time_limit_minutes: Optional[int]
    sections: List[SectionResponse]

    model_config = {
        "from_attributes": True
    }

# ---------------------------
# Teacher/Admin schemas (extend base)
# ---------------------------

class QuestionTeacherResponse(QuestionResponse):
    # teacher-only fields
    correct_answer: Optional[Any] = None
    rubric: Optional[Any] = None
    explanation: Optional[str] = None

    # stats
    usage_count: Optional[int] = None
    success_rate: Optional[float] = None

    # internal metadata (full)
    internal_metadata: Optional[Any] = None

    model_config = {
        "from_attributes": True
    }

class PartTeacherResponse(PartResponse):
    questions: List[QuestionTeacherResponse]

    model_config = {
        "from_attributes": True
    }

class SectionTeacherResponse(SectionResponse):
    parts: List[PartTeacherResponse]
    # optional: original structure link
    structure_section_id: Optional[UUID4] = None

    model_config = {
        "from_attributes": True
    }

class TestTeacherResponse(TestResponse):
    sections: List[SectionTeacherResponse]
    created_by: Optional[UUID4] = None
    updated_by: Optional[UUID4] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    exam_type_id: Optional[UUID4] = None
    structure_id: Optional[UUID4] = None

    model_config = {
        "from_attributes": True
    }
