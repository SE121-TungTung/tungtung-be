import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, UploadFile

from app.services.test.test_attempt_service import attempt_service
from app.models.test import (
    Test, TestAttempt, TestQuestion, TestResponse, QuestionBank,
    AttemptStatus, QuestionType, SkillArea
)
from app.schemas.test.test_attempt import (
    SubmitAttemptRequest, QuestionSubmitItem
)
# Import UploadType để mock
from app.models.file_upload import UploadType

# =======================================================
# 1. TEST START ATTEMPT
# =======================================================
def test_start_attempt_success_new(mock_db_session):
    # --- Arrange ---
    test_id = uuid4()
    student_id = uuid4()
    
    mock_test = MagicMock(spec=Test)
    mock_test.id = test_id
    mock_test.start_time = None
    mock_test.end_time = None
    mock_test.max_attempts = 2
    mock_test.time_limit_minutes = 60
    
    # Mock DB Query Chain
    mock_db_session.query.return_value.filter.return_value.first.side_effect = [
        mock_test,  # Call 1: Get Test
        None        # Call 3: Check existing attempt -> None
    ]
    mock_db_session.query.return_value.filter.return_value.count.return_value = 0
    
    # ✅ FIX 1: Mock db.refresh để điền đủ dữ liệu bắt buộc cho Schema StartAttemptResponse
    def side_effect_refresh(obj):
        obj.id = uuid4()
        obj.test_id = test_id          # Bắt buộc
        obj.attempt_number = 1         # Bắt buộc
        obj.started_at = datetime.now(timezone.utc) # Bắt buộc
    
    mock_db_session.refresh.side_effect = side_effect_refresh

    # --- Act ---
    result = attempt_service.start_attempt(mock_db_session, test_id, student_id)

    # --- Assert ---
    assert mock_db_session.add.call_count == 1
    assert mock_db_session.commit.called
    assert result.attempt_number == 1
    assert result.remaining_seconds == 3600

def test_start_attempt_resume_existing(mock_db_session):
    # --- Arrange ---
    test_id = uuid4()
    student_id = uuid4()
    
    mock_test = MagicMock(spec=Test)
    mock_test.id = test_id 
    mock_test.time_limit_minutes = 60
    mock_test.start_time = None 
    mock_test.end_time = None   
    
    # ✅ FIX 2: Gán giá trị cụ thể cho max_attempts để tránh lỗi so sánh (int vs MagicMock)
    mock_test.max_attempts = 10 
    
    # Existing attempt phải có đủ field
    existing_attempt = MagicMock(spec=TestAttempt)
    existing_attempt.id = uuid4()
    existing_attempt.test_id = test_id # Bắt buộc
    existing_attempt.started_at = datetime.now(timezone.utc)
    existing_attempt.attempt_number = 1
    
    mock_db_session.query.return_value.filter.return_value.first.side_effect = [
        mock_test, 
        existing_attempt 
    ]
    mock_db_session.query.return_value.filter.return_value.count.return_value = 1

    # --- Act ---
    result = attempt_service.start_attempt(mock_db_session, test_id, student_id)

    # --- Assert ---
    assert mock_db_session.add.call_count == 0 
    assert result.attempt_id == existing_attempt.id

def test_start_attempt_fail_max_attempts(mock_db_session):
    # --- Arrange ---
    mock_test = MagicMock(spec=Test)
    mock_test.max_attempts = 1 # Max 1 lần
    mock_test.start_time = None
    mock_test.end_time = None
    
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_test
    mock_db_session.query.return_value.filter.return_value.count.return_value = 1 # Đã làm 1 lần

    # --- Act & Assert ---
    with pytest.raises(HTTPException, match="Max attempts reached"):
        attempt_service.start_attempt(mock_db_session, uuid4(), uuid4())

# =======================================================
# 2. TEST SUBMIT ATTEMPT (AUTO GRADE)
# =======================================================
@pytest.mark.asyncio
async def test_submit_attempt_auto_grade(mock_db_session):
    # --- Arrange ---
    attempt_id = uuid4()
    user_id = uuid4()
    test_id = uuid4()
    
    mock_attempt = MagicMock(spec=TestAttempt)
    mock_attempt.id = attempt_id
    mock_attempt.student_id = user_id
    mock_attempt.test_id = test_id
    mock_attempt.status = AttemptStatus.IN_PROGRESS
    mock_attempt.started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    mock_attempt.test = MagicMock(passing_score=5.0)
    
    q_id = uuid4()
    mock_qb = MagicMock(spec=QuestionBank)
    mock_qb.id = q_id
    mock_qb.question_type = QuestionType.MULTIPLE_CHOICE
    mock_qb.correct_answer = "A"
    
    mock_db_session.query.return_value.join.return_value.filter.return_value.all.return_value = [
        (mock_qb, 10.0) 
    ]
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_attempt

    # ✅ FIX 3: Sử dụng 'responses' (tên alias trong schema) thay vì 'answers' khi khởi tạo
    req = SubmitAttemptRequest(
        responses=[
            QuestionSubmitItem(
                question_id=q_id,
                response_data={"selected": "A"}
            )
        ]
    )

    # --- Act ---
    result = await attempt_service.submit_attempt(mock_db_session, attempt_id, req, user_id)

    # --- Assert ---
    assert result.status == AttemptStatus.GRADED.value
    assert result.total_score == 10.0
    assert result.question_results[0].is_correct is True

# =======================================================
# 3. TEST SUBMIT ATTEMPT (WRITING / AI)
# =======================================================
@pytest.mark.asyncio
async def test_submit_attempt_writing_ai(mock_db_session):
    # --- Arrange ---
    attempt_id = uuid4()
    user_id = uuid4()
    q_id = uuid4()
    
    mock_attempt = MagicMock(spec=TestAttempt)
    mock_attempt.id = attempt_id
    mock_attempt.student_id = user_id
    mock_attempt.status = AttemptStatus.IN_PROGRESS
    mock_attempt.started_at = datetime.now(timezone.utc)
    
    mock_qb = MagicMock(spec=QuestionBank)
    mock_qb.id = q_id
    mock_qb.question_type = QuestionType.WRITING_TASK_2
    
    mock_db_session.query.return_value.join.return_value.filter.return_value.all.return_value = [
        (mock_qb, 10.0)
    ]
    mock_db_session.query.return_value.filter.return_value.first.return_value = mock_attempt

    # ✅ FIX 3: Sử dụng 'responses'
    req = SubmitAttemptRequest(
        responses=[
            QuestionSubmitItem(question_id=q_id, response_text="My Essay")
        ]
    )

    with patch("app.services.test.test_attempt_service.ai_grade_service") as mock_ai:
        mock_ai.ai_grade_writing = AsyncMock(return_value={
            "raw": {
                "overallScore": 6.5,
                "detailedFeedback": "Good job"
            }
        })
        
        # --- Act ---
        result = await attempt_service.submit_attempt(mock_db_session, attempt_id, req, user_id)

        # --- Assert ---
        assert result.status == AttemptStatus.SUBMITTED.value
        assert result.question_results[0].ai_band_score == 6.5

# =======================================================
# 4. TEST SUBMIT SPEAKING
# =======================================================
@pytest.mark.asyncio
async def test_submit_speaking_success(mock_db_session):
    # --- Arrange ---
    attempt_id = uuid4()
    question_id = uuid4()
    user_id = uuid4()
    
    mock_attempt = MagicMock(spec=TestAttempt)
    mock_attempt.student_id = user_id
    mock_attempt.test_id = uuid4()
    
    mock_question = MagicMock(spec=QuestionBank)
    mock_question.id = question_id
    mock_question.question_type = QuestionType.SPEAKING_PART_1
    
    mock_tq = MagicMock(points=10.0)
    
    mock_db_session.query.return_value.filter.return_value.first.side_effect = [
        mock_attempt,
        mock_question,
        mock_tq,
        None 
    ]

    mock_file = UploadFile(filename="voice.mp3", file=MagicMock())

    # ✅ FIX 4: Mock UploadType trong service vì Enum thật thiếu attribute
    with patch("app.services.test.test_attempt_service.UploadType") as MockUploadType:
        MockUploadType.ASSIGNMENT_SUBMISSION = "assignment_submission"
        
        with patch("app.services.test.test_attempt_service.upload_and_save_metadata", new_callable=AsyncMock) as mock_upload, \
             patch("app.services.test.test_attempt_service.ai_grade_service") as mock_ai:
            
            mock_upload.return_value = MagicMock(file_path="http://cloudinary/voice.mp3", id=uuid4())
            mock_ai.ai_grade_speaking = AsyncMock(return_value={
                "raw": {"overallScore": 7.0, "detailedFeedback": "Clear voice"}
            })

            # --- Act ---
            result = await attempt_service.submit_speaking(
                mock_db_session, attempt_id, question_id, mock_file, user_id
            )

            # --- Assert ---
            assert result["status"] == "success"
            assert result["ai_band_score"] == 7.0
            assert mock_attempt.status == AttemptStatus.SUBMITTED

# =======================================================
# 5. TEST GET ATTEMPT DETAIL
# =======================================================
def test_get_attempt_detail(mock_db_session):
    # --- Arrange ---
    attempt_id = uuid4()
    user_id = uuid4()
    
    # ✅ FIX 6: Gán các giá trị cụ thể cho Mock để Pydantic validate
    mock_attempt = MagicMock(spec=TestAttempt)
    mock_attempt.id = attempt_id
    mock_attempt.student_id = user_id
    mock_attempt.test = MagicMock(title="Test Title") # Nested mock
    mock_attempt.test_id = uuid4()
    mock_attempt.status = AttemptStatus.GRADED
    
    # Các field bắt buộc khác trong TestAttemptDetailResponse
    mock_attempt.started_at = datetime.now(timezone.utc)
    mock_attempt.submitted_at = datetime.now(timezone.utc)
    mock_attempt.time_taken_seconds = 120
    mock_attempt.total_score = 5.0
    mock_attempt.percentage_score = 50.0
    mock_attempt.band_score = None
    mock_attempt.passed = True
    mock_attempt.ai_feedback = None
    mock_attempt.teacher_feedback = None
    mock_attempt.graded_by = None
    mock_attempt.ip_address = None
    mock_attempt.user_agent = None

    # Mock responses query
    mock_resp = MagicMock(spec=TestResponse)
    mock_resp.question_id = uuid4()
    # FIX: Gán giá trị cụ thể cho QuestionResultDetail
    mock_resp.points_earned = 5.0
    mock_resp.audio_response_url = None
    mock_resp.response_text = "Ans"
    mock_resp.is_correct = True
    mock_resp.auto_graded = True
    mock_resp.ai_points_earned = None
    mock_resp.ai_feedback = None
    mock_resp.teacher_points_earned = None
    mock_resp.teacher_feedback = None
    mock_resp.time_spent_seconds = 10
    mock_resp.flagged_for_review = False
    
    mock_qb = MagicMock(spec=QuestionBank)
    mock_qb.question_text = "ABC"
    
    mock_db_session.query.return_value.options.return_value.filter.return_value.first.return_value = mock_attempt
    mock_db_session.query.return_value.join.return_value.join.return_value.filter.return_value.all.return_value = [
        (mock_resp, mock_qb, 10.0) # 10.0 là max_points
    ]

    # --- Act ---
    result = attempt_service.get_attempt_detail(mock_db_session, attempt_id, user_id)

    # --- Assert ---
    assert result.id == attempt_id
    assert result.test_title == "Test Title"
    assert len(result.details) == 1
    assert result.details[0].points_earned == 5.0

# =======================================================
# 6. HELPER METHODS
# =======================================================
def test_helper_check_answer_correctness():
    assert attempt_service._check_answer_correctness(["A"], "A", QuestionType.MULTIPLE_CHOICE) is True
    assert attempt_service._check_answer_correctness("  TrUe ", "TRUE", QuestionType.TRUE_FALSE_NOT_GIVEN) is True

def test_helper_calculate_band_score():
    assert attempt_service._calculate_band_score(100) == 9.0
    assert attempt_service._calculate_band_score(50) == 4.5