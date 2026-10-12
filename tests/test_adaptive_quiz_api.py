import pytest
from unittest.mock import MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import UserRole, UserStatus
from app.models.adaptive_quiz import AdaptiveQuizSession, AdaptiveQuizResponse, AdaptiveSessionStatus
from app.models.test import QuestionBank, QuestionType, SkillArea, DifficultyLevel, ContentStatus
from app.core.database import get_db
from app.dependencies import (
    get_current_active_user,
    require_role,
    require_any_role,
)

client = TestClient(app, base_url="http://testserver/api/v1")


def create_mock_user(role=UserRole.STUDENT):
    user = MagicMock()
    user.id = uuid4()
    user.role = role
    user.status = UserStatus.ACTIVE
    return user


student_user = create_mock_user(UserRole.STUDENT)
guest_user = create_mock_user(UserRole.GUEST_STUDENT)
teacher_user = create_mock_user(UserRole.TEACHER)
admin_user = create_mock_user(UserRole.SYSTEM_ADMIN)


@pytest.fixture(autouse=True)
def cleanup_overrides():
    yield
    app.dependency_overrides.clear()


def override_user(user):
    app.dependency_overrides[get_current_active_user] = lambda: user
    # Also override require_any_role and require_role
    for key in list(app.dependency_overrides.keys()):
        pass


def test_start_session_student(mock_db_session):
    app.dependency_overrides[get_db] = lambda: mock_db_session
    app.dependency_overrides[get_current_active_user] = lambda: student_user

    mock_db_session.query.return_value.filter.return_value.first.return_value = None
    mock_db_session.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

    res = client.post(
        "/adaptive-quiz/sessions",
        json={"skill_area": "reading", "max_items": 20},
        headers={"Authorization": "Bearer mock-token"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["data"]["skill_area"] == "reading"
    assert data["data"]["status"] == "in_progress"


def test_guest_student_limit(mock_db_session):
    app.dependency_overrides[get_db] = lambda: mock_db_session
    app.dependency_overrides[get_current_active_user] = lambda: guest_user

    # Mock count_today_sessions returns 3
    mock_db_session.query.return_value.filter.return_value.scalar.return_value = 3

    res = client.post(
        "/adaptive-quiz/sessions",
        json={"skill_area": "reading", "max_items": 20},
        headers={"Authorization": "Bearer mock-token"},
    )
    assert res.status_code == 429
    data = res.json()
    assert data["success"] is False
    assert data["error"]["code"] == "GUEST_SESSION_LIMIT_EXCEEDED"


def test_next_question_does_not_leak_answers(mock_db_session):
    session_id = uuid4()
    app.dependency_overrides[get_db] = lambda: mock_db_session
    app.dependency_overrides[get_current_active_user] = lambda: student_user

    mock_session = AdaptiveQuizSession(
        id=session_id,
        user_id=student_user.id,
        skill_area="reading",
        theta_current=0.0,
        se_current=1.0,
        items_administered=0,
        max_items=20,
        status="in_progress",
    )

    q_id = uuid4()
    mock_question = QuestionBank(
        id=q_id,
        title="Sample Question",
        question_text="What is X?",
        question_type=QuestionType.MULTIPLE_CHOICE,
        skill_area=SkillArea.READING,
        difficulty_level=DifficultyLevel.MEDIUM,
        options=[{"id": "A", "text": "Option A"}],
        correct_answer="A",
        explanation="Secret explanation",
        irt_discrimination=1.2,
        irt_difficulty=0.1,
        irt_guessing=0.25,
        irt_calibrated=True,
        is_cat_eligible=True,
        status=ContentStatus.ACTIVE,
    )

    def query_side_effect(model):
        m = MagicMock()
        if model == AdaptiveQuizSession:
            m.options.return_value.filter.return_value.first.return_value = mock_session
            m.filter.return_value.first.return_value = mock_session
        elif model == AdaptiveQuizResponse:
            m.options.return_value.filter.return_value.order_by.return_value.all.return_value = []
            m.filter.return_value.all.return_value = []
        elif model == QuestionBank:
            m.filter.return_value.all.return_value = [mock_question]
        return m

    mock_db_session.query.side_effect = query_side_effect

    res = client.get(f"/adaptive-quiz/sessions/{session_id}/next-question")
    assert res.status_code == 200
    data = res.json()["data"]
    assert "correct_answer" not in data
    assert "explanation" not in data
    assert data["title"] == "Sample Question"
    assert data["question_id"] == str(q_id)


def test_rbac_student_cannot_update_irt(mock_db_session):
    q_id = uuid4()
    app.dependency_overrides[get_db] = lambda: mock_db_session
    app.dependency_overrides[get_current_active_user] = lambda: student_user

    res = client.put(
        f"/adaptive-quiz/questions/{q_id}/irt",
        json={"irt_discrimination": 1.5, "irt_difficulty": 0.5, "irt_guessing": 0.25},
    )
    assert res.status_code == 403


def test_rbac_staff_can_view_stats(mock_db_session):
    app.dependency_overrides[get_db] = lambda: mock_db_session
    app.dependency_overrides[get_current_active_user] = lambda: teacher_user

    # Mock count queries for stats
    mock_db_session.query.return_value.filter.return_value.count.return_value = 50
    mock_db_session.query.return_value.filter.return_value.scalar.return_value = 0.5

    res = client.get("/adaptive-quiz/calibration-stats")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "total_questions" in data["data"]


def test_rbac_sysadmin_can_calibrate(mock_db_session):
    app.dependency_overrides[get_db] = lambda: mock_db_session
    app.dependency_overrides[get_current_active_user] = lambda: admin_user

    mock_db_session.query.return_value.filter.return_value.all.return_value = []

    res = client.post(
        "/adaptive-quiz/calibrate",
        json={"min_responses": 20},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "calibrated_items_count" in data["data"]


def test_submit_response_updates_theta(mock_db_session):
    session_id = uuid4()
    q_id = uuid4()
    app.dependency_overrides[get_db] = lambda: mock_db_session
    app.dependency_overrides[get_current_active_user] = lambda: student_user

    mock_session = AdaptiveQuizSession(
        id=session_id,
        user_id=student_user.id,
        skill_area="reading",
        theta_current=0.0,
        se_current=1.0,
        items_administered=0,
        max_items=20,
        status="in_progress",
        theta_history=[],
    )

    mock_question = QuestionBank(
        id=q_id,
        title="Sample Question",
        question_text="What is X?",
        question_type=QuestionType.MULTIPLE_CHOICE,
        skill_area=SkillArea.READING,
        options=[{"id": "A", "text": "Option A"}],
        correct_answer="A",
        irt_discrimination=1.2,
        irt_difficulty=0.1,
        irt_guessing=0.25,
        irt_calibrated=True,
        is_cat_eligible=True,
        status=ContentStatus.ACTIVE,
    )

    def query_side_effect(model):
        m = MagicMock()
        if model == AdaptiveQuizSession:
            m.options.return_value.filter.return_value.first.return_value = mock_session
            m.filter.return_value.first.return_value = mock_session
        elif model == AdaptiveQuizResponse:
            m.options.return_value.filter.return_value.order_by.return_value.all.return_value = []
            m.filter.return_value.all.return_value = []
            m.filter.return_value.first.return_value = None
        elif model == QuestionBank:
            m.filter.return_value.first.return_value = mock_question
            m.filter.return_value.all.return_value = [mock_question]
        return m

    mock_db_session.query.side_effect = query_side_effect

    res = client.post(
        f"/adaptive-quiz/sessions/{session_id}/responses",
        json={"question_id": str(q_id), "response_data": "A", "time_spent_seconds": 35},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    res_data = data["data"]
    assert res_data["is_correct"] is True
    assert res_data["item_position"] == 1
    assert "theta_after" in res_data
    assert "se_after" in res_data

