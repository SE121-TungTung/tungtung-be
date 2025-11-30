from pydantic import BaseModel, Field, validator
from uuid import UUID
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal

# ============================================
# SOURCE MATERIAL SCHEMAS
# ============================================

class SourceMaterialBase(BaseModel):
    title: str = Field(..., max_length=255)
    content_type: str = Field(..., description="text, audio, prompt, topic_card")
    content_text: Optional[str] = None
    file_upload_id: Optional[UUID] = None
    word_count: Optional[int] = Field(None, ge=0)
    duration_seconds: Optional[int] = Field(None, ge=0)
    difficulty_level: Optional[str] = Field(None, description="easy, medium, hard")

class SourceMaterialCreate(SourceMaterialBase):
    pass

class SourceMaterialUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content_text: Optional[str] = None
    difficulty_level: Optional[str] = None
    status: Optional[str] = None

class SourceMaterialResponse(SourceMaterialBase):
    id: UUID
    created_at: datetime
    created_by: UUID
    status: str
    
    class Config:
        from_attributes = True


# ============================================
# QUESTION BANK SCHEMAS
# ============================================

class QuestionBankBase(BaseModel):
    title: str = Field(..., max_length=255)
    question_text: str
    question_type: str = Field(..., description="multiple_choice, true_false_not_given, essay, etc.")
    section_type: str = Field(..., description="listening, reading, writing, speaking")
    difficulty_level: str = Field(..., description="easy, medium, hard")
    
    options: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    correct_answer: Optional[str] = None
    rubric: Optional[Dict[str, Any]] = None
    points: Decimal = Field(default=1.00, ge=0)

class QuestionBankCreate(QuestionBankBase):
    pass

class QuestionBankUpdate(BaseModel):
    title: Optional[str] = None
    question_text: Optional[str] = None
    options: Optional[List[Dict[str, Any]]] = None
    correct_answer: Optional[str] = None
    difficulty_level: Optional[str] = None
    status: Optional[str] = None

class QuestionBankResponse(QuestionBankBase):
    id: UUID
    usage_count: int
    success_rate: Optional[Decimal]
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============================================
# TEST QUESTION SCHEMAS (Questions in a Part)
# ============================================

class TestQuestionCreate(BaseModel):
    """Add a question to a specific test part"""
    question_id: UUID
    order_number: int = Field(..., ge=1, description="Question number within the part")
    points: Optional[Decimal] = Field(None, ge=0, description="Override points if needed")
    required: bool = True

class TestQuestionBulkCreate(BaseModel):
    """Bulk add questions to a part"""
    question_ids: List[UUID] = Field(..., min_items=1)
    start_order_number: int = Field(1, ge=1, description="Starting question number")

class TestQuestionResponse(BaseModel):
    id: UUID
    part_id: UUID
    question_id: UUID
    order_number: int
    points: Optional[Decimal]
    required: bool
    
    # Include question details
    question: Optional[QuestionBankResponse] = None
    
    class Config:
        from_attributes = True


# ============================================
# TEST PART SCHEMAS (Parts within a Section)
# ============================================

class TestPartCreate(BaseModel):
    """Create a part within a section (e.g., Reading Passage 1)"""
    part_number: int = Field(..., ge=1, description="1, 2, 3, or 4")
    title: str = Field(..., max_length=255, description="'Part 1', 'Passage 1', 'Task 1'")
    source_material_id: Optional[UUID] = Field(None, description="Shared passage/audio for all questions in this part")
    instructions: Optional[str] = None
    time_limit_minutes: Optional[int] = Field(None, ge=1)
    order_number: int = Field(..., ge=1, description="Order within section")

class TestPartUpdate(BaseModel):
    title: Optional[str] = None
    source_material_id: Optional[UUID] = None
    instructions: Optional[str] = None
    time_limit_minutes: Optional[int] = None

class TestPartResponse(BaseModel):
    id: UUID
    section_id: UUID
    part_number: int
    title: str
    source_material_id: Optional[UUID]
    instructions: Optional[str]
    time_limit_minutes: Optional[int]
    order_number: int
    
    # Include questions in this part
    questions: List[TestQuestionResponse] = []
    
    # Include source material details
    source_material: Optional[SourceMaterialResponse] = None
    
    class Config:
        from_attributes = True


# ============================================
# TEST SECTION SCHEMAS (Listening, Reading, etc.)
# ============================================

class TestSectionCreate(BaseModel):
    """Create a section within a test (e.g., Listening Section)"""
    section_type: str = Field(..., description="listening, reading, writing, speaking")
    order_number: int = Field(..., ge=1, description="1, 2, 3, or 4")
    title: str = Field(..., max_length=255, description="'Listening Section', 'Reading Section'")
    instructions: Optional[str] = None
    time_limit_minutes: int = Field(..., ge=1, description="30 for Listening, 60 for Reading, etc.")

class TestSectionUpdate(BaseModel):
    title: Optional[str] = None
    instructions: Optional[str] = None
    time_limit_minutes: Optional[int] = None

class TestSectionResponse(BaseModel):
    id: UUID
    test_id: UUID
    section_type: str
    order_number: int
    title: str
    instructions: Optional[str]
    time_limit_minutes: int
    total_points: Decimal
    
    # Include all parts in this section
    parts: List[TestPartResponse] = []
    
    class Config:
        from_attributes = True


# ============================================
# TEST SCHEMAS (Main Test)
# ============================================

class TestCreate(BaseModel):
    """Create a complete IELTS test"""
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    test_code: Optional[str] = Field(None, max_length=50, description="e.g., IELTS-2024-01")
    is_official: bool = False
    
    class_id: Optional[UUID] = None
    
    # Test settings
    time_limit_minutes: int = Field(165, ge=1, description="Total test time (usually 165 mins)")
    passing_score: Decimal = Field(60, ge=0, le=100)
    max_attempts: int = Field(1, ge=1)
    
    # Behavior settings
    randomize_questions: bool = False
    show_results_immediately: bool = False
    allow_section_navigation: bool = False
    
    # Scheduling
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    instructions: Optional[str] = None
    ai_grading_enabled: bool = True

class TestUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    time_limit_minutes: Optional[int] = None
    passing_score: Optional[Decimal] = None
    status: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

class TestResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    test_code: Optional[str]
    is_official: bool
    
    created_by: UUID
    class_id: Optional[UUID]
    
    total_points: Decimal
    time_limit_minutes: int
    passing_score: Decimal
    max_attempts: int
    
    status: str
    created_at: datetime
    
    # Include all sections
    sections: List[TestSectionResponse] = []
    
    class Config:
        from_attributes = True

class TestListResponse(BaseModel):
    """Simplified response for listing tests"""
    id: UUID
    title: str
    test_code: Optional[str]
    is_official: bool
    status: str
    total_points: Decimal
    time_limit_minutes: int
    created_at: datetime
    
    # Summary stats
    total_sections: int = 0
    total_questions: int = 0
    
    class Config:
        from_attributes = True


# ============================================
# TEST ATTEMPT SCHEMAS
# ============================================

class TestAttemptStart(BaseModel):
    """Start a new test attempt"""
    test_id: UUID
    # student_id will be taken from current_user, no need in request body

class TestAttemptResponse(BaseModel):
    id: UUID
    test_id: UUID
    student_id: UUID
    attempt_number: int
    
    started_at: datetime
    submitted_at: Optional[datetime]
    time_taken_seconds: Optional[int]
    
    # Scores
    total_score: Optional[Decimal]
    percentage_score: Optional[Decimal]
    overall_band_score: Optional[Decimal]
    
    listening_band_score: Optional[Decimal]
    reading_band_score: Optional[Decimal]
    writing_band_score: Optional[Decimal]
    speaking_band_score: Optional[Decimal]
    
    passed: Optional[bool]
    status: str
    
    # Feedback
    ai_feedback: Optional[Dict[str, Any]]
    teacher_feedback: Optional[str]
    graded_by: Optional[UUID]
    graded_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class TestAttemptSubmit(BaseModel):
    """Submit a completed test attempt"""
    # All responses should already be saved via TestResponseCreate
    # This just marks the attempt as submitted
    pass


# ============================================
# SECTION ATTEMPT SCHEMAS (NEW)
# ============================================

class SectionAttemptStart(BaseModel):
    """Start working on a specific section"""
    section_id: UUID

class SectionAttemptComplete(BaseModel):
    """Mark a section as completed"""
    section_id: UUID

class SectionAttemptResponse(BaseModel):
    id: UUID
    test_attempt_id: UUID
    section_id: UUID
    
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    time_taken_seconds: Optional[int]
    
    section_score: Optional[Decimal]
    band_score: Optional[Decimal]
    
    class Config:
        from_attributes = True


# ============================================
# TEST RESPONSE SCHEMAS (Individual Answers)
# ============================================

class TestResponseCreate(BaseModel):
    """Save/update a student's answer to a question"""
    question_id: UUID
    response_text: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None
    audio_response_url: Optional[str] = None
    time_spent_seconds: Optional[int] = Field(None, ge=0)
    flagged_for_review: bool = False

class TestResponseUpdate(BaseModel):
    """Update an existing response"""
    response_text: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None
    flagged_for_review: Optional[bool] = None

class TestResponseDetail(BaseModel):
    id: UUID
    attempt_id: UUID
    question_id: UUID
    
    # Student's answer
    response_text: Optional[str]
    response_data: Optional[Dict[str, Any]]
    audio_response_url: Optional[str]
    
    # Grading
    is_correct: Optional[bool]
    points_earned: Decimal
    
    ai_score: Optional[Decimal]
    ai_feedback: Optional[str]
    
    teacher_score: Optional[Decimal]
    teacher_feedback: Optional[str]
    
    time_spent_seconds: Optional[int]
    flagged_for_review: bool
    
    class Config:
        from_attributes = True


# ============================================
# GRADING SCHEMAS
# ============================================

class AutoGradeRequest(BaseModel):
    """Request AI grading for essay/speaking responses"""
    attempt_id: UUID
    question_ids: Optional[List[UUID]] = None  # If None, grade all ungraded

class ManualGradeRequest(BaseModel):
    """Teacher manually grades a response"""
    response_id: UUID
    teacher_score: Decimal = Field(..., ge=0)
    teacher_feedback: Optional[str] = None

class GradingResponse(BaseModel):
    response_id: UUID
    question_id: UUID
    points_earned: Decimal
    feedback: Optional[str]
    graded_by: str  # "AI" or teacher name
    
    class Config:
        from_attributes = True


# ============================================
# BULK OPERATIONS
# ============================================

class BulkTestCreation(BaseModel):
    """
    Create a complete IELTS test with all sections, parts, and questions in one go
    Useful for importing tests from external sources
    """
    test_info: TestCreate
    sections: List[Dict[str, Any]] = Field(
        ..., 
        description="List of sections with nested parts and questions"
    )
    
    # Example structure:
    # sections: [
    #   {
    #     "section_type": "listening",
    #     "title": "Listening Section",
    #     "time_limit_minutes": 30,
    #     "parts": [
    #       {
    #         "part_number": 1,
    #         "title": "Part 1",
    #         "source_material_id": "uuid",
    #         "questions": [
    #           {"question_id": "uuid", "order_number": 1},
    #           {"question_id": "uuid", "order_number": 2}
    #         ]
    #       }
    #     ]
    #   }
    # ]


# ============================================
# ANALYTICS & STATISTICS
# ============================================

class TestStatistics(BaseModel):
    """Statistics for a test"""
    test_id: UUID
    total_attempts: int
    average_score: Optional[Decimal]
    average_band_score: Optional[Decimal]
    pass_rate: Optional[Decimal]
    
    # Section statistics
    section_stats: List[Dict[str, Any]] = []
    
    # Question difficulty analysis
    difficult_questions: List[Dict[str, Any]] = []

class StudentProgress(BaseModel):
    """Track student's progress on a test"""
    attempt_id: UUID
    test_id: UUID
    
    total_questions: int
    answered_questions: int
    flagged_questions: int
    
    current_section: Optional[str]
    time_remaining_seconds: Optional[int]
    
    progress_percentage: Decimal = Field(..., ge=0, le=100)


# ============================================
# VALIDATION HELPERS
# ============================================

@validator('section_type')
def validate_section_type(cls, v):
    valid_sections = ['listening', 'reading', 'writing', 'speaking']
    if v not in valid_sections:
        raise ValueError(f'section_type must be one of {valid_sections}')
    return v

@validator('question_type')  
def validate_question_type(cls, v):
    valid_types = [
        'multiple_choice', 'true_false_not_given', 'yes_no_not_given',
        'matching', 'sentence_completion', 'summary_completion',
        'short_answer', 'essay', 'letter', 'speaking_response'
    ]
    if v not in valid_types:
        raise ValueError(f'question_type must be one of {valid_types}')
    return v