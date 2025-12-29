import pytest
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock
from fastapi import HTTPException, UploadFile
from datetime import datetime

# ✅ FIX: Import đúng tên class từ schema
from app.schemas.test.test_create import (
    TestCreate, 
    TestSectionCreate, 
    TestSectionPartCreate, 
    QuestionGroupCreate, 
    QuestionCreate
)
from app.models.test import (
    Test, TestStatus, TestType, SkillArea, 
    QuestionType, QuestionBank
)
from app.services.test.test import test_service

# ==========================================
# 1. TEST CREATE TEST
# ==========================================
@pytest.mark.asyncio
async def test_create_test_success(mock_db_session, mock_upload_service, sample_user_id):
    # ... (Giữ nguyên phần Arrange data đầu vào) ...
    question_data = QuestionCreate(
        title="Q1",
        question_text="What is 1+1?",
        question_type=QuestionType.MULTIPLE_CHOICE,
        points=1.0,
        audio_url="file:q1_audio.mp3",
        skill_area=SkillArea.READING
    )
    
    group_data = QuestionGroupCreate(
        name="Group 1",
        order_number=1,
        question_type=QuestionType.MULTIPLE_CHOICE,
        questions=[question_data],
        image_url="file:group_img.png"
    )
    
    part_data = TestSectionPartCreate(
        name="Part 1",
        order_number=1,
        question_groups=[group_data],
        audio_url="file:part_audio.mp3",
        structure_part_id=None
    )
    
    section_data = TestSectionCreate(
        name="Section 1",
        skill_area=SkillArea.READING,
        order_number=1,
        parts=[part_data],
        structure_section_id=None
    )
    
    test_create_data = TestCreate(
        title="Unit Test Exam",
        test_type=TestType.QUIZ,
        sections=[section_data],
        exam_type_id=None, 
        structure_id=None
    )

    mock_files = [
        UploadFile(filename="q1_audio.mp3", file=MagicMock()),
        UploadFile(filename="group_img.png", file=MagicMock()),
        UploadFile(filename="part_audio.mp3", file=MagicMock())
    ]

    mock_db_session.query.return_value.filter.return_value.first.return_value = None

    # --- Act ---
    result = await test_service.create_test(
        db=mock_db_session,
        data=test_create_data,
        created_by=sample_user_id,
        files=mock_files
    )

    # --- Assert ---
    assert mock_db_session.add.call_count >= 6 
    assert mock_db_session.commit.called
    assert mock_upload_service.call_count == 3

# ==========================================
# 2. TEST GET TEST (Fix Pydantic Error)
# ==========================================
def test_get_test_for_student_success(mock_db_session):
    # --- Arrange ---
    test_id = uuid4()
    
    # FIX: Gán giá trị cụ thể cho Mock Object để Pydantic validate
    mock_test = MagicMock(spec=Test)
    mock_test.id = test_id
    mock_test.title = "Sample Test Title"          # str
    mock_test.description = "Sample Desc"          # str
    mock_test.instructions = "Do this"             # str
    mock_test.test_type = TestType.QUIZ            # Enum
    mock_test.time_limit_minutes = 60              # int
    mock_test.total_points = 100.0                 # float
    mock_test.passing_score = 50.0                 # float
    mock_test.max_attempts = 1                     # int
    mock_test.randomize_questions = False          # bool
    mock_test.show_results_immediately = True      # bool
    mock_test.status = TestStatus.PUBLISHED        # Enum
    mock_test.ai_grading_enabled = False           # bool
    mock_test.start_time = None
    mock_test.end_time = None
    
    # Relationships (Empty list for simplicity)
    mock_test.sections = [] 
    
    # Mock Query Chain
    mock_query = mock_db_session.query.return_value
    mock_query.options.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = mock_test

    # --- Act ---
    result = test_service.get_test_for_student(mock_db_session, test_id)

    # --- Assert ---
    assert result.id == test_id
    assert result.title == "Sample Test Title"

def test_get_test_for_teacher_success(mock_db_session):
    # --- Arrange ---
    test_id = uuid4()
    user_id = uuid4()
    
    # FIX: Gán đầy đủ giá trị cho Teacher Response (nhiều field hơn Student)
    mock_test = MagicMock(spec=Test)
    mock_test.id = test_id
    mock_test.title = "Teacher Test"
    mock_test.description = "Desc"
    mock_test.instructions = "Instr"
    mock_test.test_type = TestType.FINAL
    mock_test.time_limit_minutes = 90
    mock_test.total_points = 100.0
    mock_test.passing_score = 60.0
    mock_test.max_attempts = 2
    mock_test.randomize_questions = True
    mock_test.show_results_immediately = False
    mock_test.status = TestStatus.DRAFT
    mock_test.ai_grading_enabled = True
    mock_test.start_time = datetime.now()
    mock_test.end_time = datetime.now()
    
    # Audit fields
    mock_test.created_by = user_id
    mock_test.created_at = datetime.now()
    mock_test.updated_at = datetime.now()
    mock_test.class_id = None
    mock_test.course_id = None
    mock_test.exam_type_id = None
    mock_test.structure_id = None
    
    mock_test.sections = [] 

    mock_query = mock_db_session.query.return_value
    mock_query.options.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = mock_test

    # --- Act ---
    result = test_service.get_test_for_teacher(mock_db_session, test_id)

    # --- Assert ---
    assert result.id == test_id
    assert result.created_by == user_id

def test_get_test_not_found(mock_db_session):
    # --- Arrange ---
    mock_db_session.query.return_value.options.return_value.filter.return_value.filter.return_value.first.return_value = None
    
    # --- Act & Assert ---
    with pytest.raises(HTTPException) as exc:
        test_service.get_test_for_student(mock_db_session, uuid4())
    assert exc.value.status_code == 404

# ==========================================
# 3. TEST LIST TESTS
# ==========================================
def test_list_tests_filters(mock_db_session):
    # --- Arrange ---
    # Mock list of tests
    # Cần mock attribute sections và questions cho eager loading
    t1 = MagicMock(spec=Test)
    t1.id = uuid4()
    t1.title = "Test 1"
    t1.sections = [MagicMock(skill_area=SkillArea.READING)]
    t1.questions = [MagicMock(), MagicMock()] # 2 questions
    t1.test_type = TestType.QUIZ
    t1.status = TestStatus.PUBLISHED

    t2 = MagicMock(spec=Test)
    t2.id = uuid4()
    t2.title = "Test 2"
    t2.sections = []
    t2.questions = []
    t2.test_type = None
    t2.status = TestStatus.DRAFT
    
    mock_query = mock_db_session.query.return_value
    # Setup chaining mocks
    mock_query.filter.return_value = mock_query
    mock_query.join.return_value = mock_query
    mock_query.distinct.return_value = mock_query
    mock_query.options.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = [t1, t2]
    mock_query.count.return_value = 2

    # --- Act ---
    result = test_service.list_tests(
        db=mock_db_session, 
        status=TestStatus.PUBLISHED.value, 
        skill=SkillArea.READING.value
    )

    # --- Assert ---
    assert result["total"] == 2
    assert len(result["tests"]) == 2
    assert result["tests"][0]["title"] == "Test 1"
    assert result["tests"][0]["total_questions"] == 2
    
    # Verify filters were called
    assert mock_query.filter.call_count >= 1

# ==========================================
# 4. TEST GET SUMMARY
# ==========================================
def test_get_test_summary(mock_db_session):
    # --- Arrange ---
    test_id = uuid4()
    mock_test = MagicMock(spec=Test)
    mock_test.id = test_id
    mock_test.title = "Summary Test"
    mock_test.total_points = 100
    mock_test.test_type = TestType.FINAL
    mock_test.status = TestStatus.PUBLISHED
    
    # Mock Test Query
    # Query 1: Get Test
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_test
    
    # Mock các query count/scalar tiếp theo
    # Vì service gọi db.query() nhiều lần, ta cần config side_effect hoặc return value cho các lần gọi
    # Cách đơn giản nhất cho unit test service cô lập là mock hàm count() và scalar() của query builder
    
    # Tạo một mock query builder chung
    mock_query = mock_db_session.query.return_value
    mock_query.filter.return_value = mock_query
    mock_query.count.return_value = 10 # Default for count()
    mock_query.scalar.return_value = 85.5 # Default for scalar() (avg score)

    # --- Act ---
    result = test_service.get_test_summary(mock_db_session, test_id)

    # --- Assert ---
    assert result["id"] == test_id
    assert result["title"] == "Summary Test"
    # Logic: pass_rate = (passed_count / completed_attempts) * 100
    # count() trả về 10 cho cả passed_count và completed_attempts -> 100%
    assert result["pass_rate"] == 100.0
    assert result["average_score"] == 85.5
    assert result["total_questions"] == 10