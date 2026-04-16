import pytest
from uuid import uuid4
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.schedule.ga_service import ga_schedule_service
from app.schemas.ga_schedule import GAScheduleRequest, TeacherUnavailabilityCreate
from app.models.ga_schedule import GARun, GARunStatus, GAScheduleProposal, TeacherUnavailability
from app.models.academic import Class, Room
from app.models.user import User

@pytest.fixture
def sample_ga_request():
    return GAScheduleRequest(
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 26),
        class_ids=[uuid4(), uuid4()],
        population_size=100,
        generations=300
    )

def test_run_ga_schedule(mock_db_session, sample_ga_request):
    """Test GA run schedule triggers GARun creation properly."""
    
    # Mock commit and refresh to populate required fields
    def mock_refresh_run(obj):
        obj.id = uuid4()
        obj.created_at = datetime.now(timezone.utc)
    mock_db_session.refresh.side_effect = mock_refresh_run

    response = ga_schedule_service.run_ga_schedule(mock_db_session, sample_ga_request)
    
    assert response is not None
    assert response.status == GARunStatus.PENDING.value
    assert response.start_date == sample_ga_request.start_date
    assert response.end_date == sample_ga_request.end_date
    
    # Verify that add and commit were called
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()

def test_get_run_result_success(mock_db_session):
    """Test fetching run results."""
    run_id = uuid4()
    
    # Mock finding the GARun
    mock_run = MagicMock(spec=GARun)
    mock_run.id = run_id
    mock_run.status = GARunStatus.COMPLETED
    mock_run.deleted_at = None
    mock_run.best_fitness = 90.0
    mock_run.hard_violations = 0
    mock_run.soft_score = 90.0
    mock_run.generations_run = 50
    mock_run.start_date = date(2026, 4, 20)
    mock_run.end_date = date(2026, 4, 26)
    mock_run.started_at = datetime.now(timezone.utc)
    mock_run.completed_at = datetime.now(timezone.utc)
    mock_run.created_at = datetime.now(timezone.utc)
    mock_run.result_summary = {"total_sessions": 2, "conflict_count": 0}
    mock_run.config = {}

    # Mock DB Query for GARun
    mock_query = mock_db_session.query.return_value
    class1 = MagicMock(spec=Class)
    class1.name = "Math"
    teacher1 = MagicMock(spec=User)
    teacher1.first_name = "John"
    teacher1.last_name = "Doe"
    room1 = MagicMock(spec=Room)
    room1.name = "A1"

    class2 = MagicMock(spec=Class)
    class2.name = "Physics"
    teacher2 = MagicMock(spec=User)
    teacher2.first_name = "Jane"
    teacher2.last_name = "Doe"
    room2 = MagicMock(spec=Room)
    room2.name = "A2"

    mock_query.filter.return_value.first.side_effect = [
        mock_run, # First for GARun
        class1, teacher1, room1,
        class2, teacher2, room2,
    ]

    # Mock Proposals
    prop1 = MagicMock(spec=GAScheduleProposal)
    prop1.id = uuid4()
    prop1.class_id = uuid4()
    prop1.teacher_id = uuid4()
    prop1.room_id = uuid4()
    prop1.session_date = date(2026, 4, 20)
    prop1.time_slots = [1, 2]
    prop1.start_time = datetime.now().time()
    prop1.end_time = datetime.now().time()
    prop1.lesson_topic = "Intro"
    prop1.is_conflict = False
    prop1.conflict_details = None

    prop2 = MagicMock(spec=GAScheduleProposal)
    prop2.id = uuid4()
    prop2.class_id = uuid4()
    prop2.teacher_id = uuid4()
    prop2.room_id = uuid4()
    prop2.session_date = date(2026, 4, 21)
    prop2.time_slots = [3, 4]
    prop2.start_time = datetime.now().time()
    prop2.end_time = datetime.now().time()
    prop2.lesson_topic = "Part 2"
    prop2.is_conflict = False
    prop2.conflict_details = None

    mock_query.filter.return_value.all.return_value = [prop1, prop2]

    response = ga_schedule_service.get_run_result(mock_db_session, run_id)
    assert response.run_id == run_id
    assert response.status == GARunStatus.COMPLETED.value
    assert len(response.sessions) == 2
    assert response.total_sessions == 2
    assert response.conflict_count == 0

def test_create_teacher_unavailability(mock_db_session):
    """Test creating teacher unavailability."""
    teacher_id = uuid4()
    req = TeacherUnavailabilityCreate(
        teacher_id=teacher_id,
        unavailable_date=date(2026, 4, 25),
        is_recurring=False,
        reason="Vacation"
    )

    # Mock user query
    mock_db_session.query.return_value.filter.return_value.first.return_value = MagicMock(spec=User)
    
    # Mock commit and refresh
    def mock_refresh(obj):
        obj.id = uuid4()
        obj.created_at = datetime.now(timezone.utc)
        
    mock_db_session.refresh.side_effect = mock_refresh

    result = ga_schedule_service.create_teacher_unavailability(mock_db_session, req)
    
    assert result.teacher_id == teacher_id
    assert result.unavailable_date == req.unavailable_date
    assert result.reason == "Vacation"
    assert result.is_recurring is False
    
    mock_db_session.add.assert_called_once()
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once()
