from pydantic import BaseModel, UUID4
from typing import List, Optional, Any
from datetime import datetime
from app.models.test import SkillArea, DifficultyLevel

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
    order_number: int 
    status: str

    model_config = {
        "from_attributes": True
    }

class QuestionGroupResponse(BaseModel):
    id: UUID4
    name: str
    order_number: int

    question_type: str
    instructions: Optional[str]

    image_url: Optional[str]

    questions: List[QuestionResponse]

    model_config = {"from_attributes": True}

class PartResponse(BaseModel):
    id: UUID4
    name: str
    order_number: int
    passage: Optional["PassageResponse"] = None
    min_questions: Optional[int] = None
    max_questions: Optional[int] = None
    image_url: Optional[str] = None
    audio_url: Optional[str] = None
    instructions: Optional[str] = None
    question_groups: List[QuestionGroupResponse]

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

    total_points: float
    passing_score: float
    max_attempts: int 
    randomize_questions: bool
    show_results_immediately: bool

    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    status: str
    ai_grading_enabled: bool

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

class QuestionGroupTeacherResponse(QuestionGroupResponse):
    questions: List[QuestionTeacherResponse]

class PartTeacherResponse(PartResponse):
    structure_part_id: Optional[UUID4] = None
    question_groups: List[QuestionGroupTeacherResponse]

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

    course_id: Optional[UUID4] = None
    class_id: Optional[UUID4] = None

    reviewed_by: Optional[UUID4] = None
    reviewed_at: Optional[datetime] = None

    model_config = {
        "from_attributes": True
    }

# ---------------------------
# Additional schemas for listing tests
# ---------------------------

class TestListResponse(BaseModel):
    id: UUID4
    title: str
    description: Optional[str]
    skill: SkillArea
    difficulty: DifficultyLevel
    test_type: str
    duration_minutes: int
    total_questions: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# --- 2. Schema cho Attempt Detail ---
class QuestionResultResponse(BaseModel):
    question_id: UUID4
    question_text: str
    question_type: str

    user_answer: Optional[str]
    response_data: Optional[Any] = None
    audio_response_url: Optional[str] = None
    
    # Auto-grading (Reading/Listening)
    is_correct: Optional[bool] = None
    auto_graded: bool
    
    # Final scores
    points_earned: float
    max_points: float
    band_score: Optional[float] = None
    
    # Rubric details
    rubric_scores: Optional[dict] = None
    
    # AI grading (đổi tên cho đúng)
    ai_points_earned: Optional[float] = None
    ai_band_score: Optional[float] = None
    ai_rubric_scores: Optional[dict] = None
    ai_feedback: Optional[str] = None
    
    # Teacher override (đổi tên cho đúng)
    teacher_points_earned: Optional[float] = None
    teacher_band_score: Optional[float] = None
    teacher_rubric_scores: Optional[dict] = None
    teacher_feedback: Optional[str] = None
    
    # Metadata
    time_spent_seconds: Optional[int] = None 
    flagged_for_review: bool = False
    

class TestAttemptDetailResponse(BaseModel):
    id: UUID4
    test_id: UUID4
    test_title: str
    student_id: UUID4

    attempt_number: int
    started_at: datetime
    submitted_at: Optional[datetime] = None
    time_taken_seconds: Optional[int] = None

    total_score: Optional[float] = None
    percentage_score: Optional[float] = None
    band_score: Optional[float] = None
    passed: Optional[bool] = None

    status: str

    graded_by: Optional[UUID4] = None
    graded_at: Optional[datetime] = None
    
    # Feedback
    ai_feedback: Optional[dict] = None
    teacher_feedback: Optional[str] = None

    # Danh sách kết quả từng câu
    details: List[QuestionResultResponse] 

    class Config:
        from_attributes = True

class PassageResponse(BaseModel):
    id: UUID4
    title: str
    text_content: Optional[str] = None
    audio_url: Optional[str] = None
    image_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    
    model_config = {"from_attributes": True}
