from datetime import date, time, timedelta
from uuid import UUID
from unittest.mock import MagicMock, patch
import pytest
import math
import random
from fastapi import HTTPException

# Giả định cấu trúc import
from app.services.schedule import ScheduleService, SYSTEM_TIME_SLOTS, MAX_SLOT_NUMBER
from app.schemas.schedule import ScheduleGenerateRequest, SessionProposal, ConflictInfo

# --- MOCK OBJECTS TỐI THIỂU ---

class MockClass:
    def __init__(self, id, teacher_id, max_students, sessions_per_week, schedule, name="Test Class"):
        self.id = id
        self.teacher_id = teacher_id
        self.max_students = max_students
        self.sessions_per_week = sessions_per_week
        self.schedule = schedule
        self.name = name
        self.deleted_at = None

class MockUser:
    def __init__(self, id, first_name="John", last_name="Doe"):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name

class MockRoom:
    def __init__(self, id, name="Room A"):
        self.id = id
        self.name = name

# --- FIXTURES (Dữ liệu cố định) ---

@pytest.fixture
def mock_repos():
    """Tạo mock cho các repositories được DI vào ScheduleService."""
    repos = {
        'class_repo': MagicMock(),
        'session_repo': MagicMock(),
        'room_repo': MagicMock(),
        'user_repo': MagicMock()
    }
    return repos

@pytest.fixture
def schedule_service(mock_repos):
    """Tạo instance ScheduleService với các mock repositories."""
    service = ScheduleService(**mock_repos)
    service.SYSTEM_TIME_SLOTS = SYSTEM_TIME_SLOTS 
    return service

@pytest.fixture
def mock_data():
    """Tạo dữ liệu cơ sở cho các test case."""
    data = {
        'class_id': UUID('11111111-1111-1111-1111-111111111111'),
        'class_id_2': UUID('22222222-2222-2222-2222-222222222222'), 
        'teacher_id': UUID('33333333-3333-3333-3333-333333333333'),
        'teacher_id_2': UUID('44444444-4444-4444-4444-444444444444'), 
        'room_id': UUID('55555555-5555-5555-5555-555555555555'),
        'start_date': date(2025, 12, 1), # Monday
        'end_date': date(2025, 12, 7),   # Sunday (1 week)
    }
    data['test_class'] = MockClass(
        id=data['class_id'], teacher_id=data['teacher_id'], max_students=20,
        sessions_per_week=2, schedule=[], name="Mock 101"
    )
    data['test_class_2'] = MockClass(
        id=data['class_id_2'], teacher_id=data['teacher_id_2'], max_students=10,
        sessions_per_week=1, schedule=[], name="Mock 202"
    )
    data['test_user'] = MockUser(id=data['teacher_id'], first_name="Prof", last_name="X")
    data['test_user_2'] = MockUser(id=data['teacher_id_2'], first_name="Ms", last_name="Y")
    data['test_room'] = MockRoom(id=data['room_id'], name="Room Z")
    return data

def mock_class_query_result(db_mock, result_list, filter_count=1):
    """Hàm trợ giúp Mock chuỗi truy vấn SQLAlchemy theo số lần filter."""
    mock_chain = db_mock.query.return_value
    for _ in range(filter_count):
        mock_chain = mock_chain.filter.return_value
    mock_chain.all.return_value = result_list

# --- TEST CASES V1 (Gốc) ---

@patch('app.services.schedule.ScheduleService._find_available_room', return_value=UUID('55555555-5555-5555-5555-555555555555'))
@patch('app.services.schedule.ScheduleService._check_teacher_conflict', return_value=False)
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_successful_schedule_generation(
    mock_select_rule, mock_check_teacher_conflict, mock_find_room, schedule_service, mock_repos, mock_data
):
    """(T1) Kiểm tra tạo lịch thành công (2 sessions) và tính toán mục tiêu đúng."""
    db_mock = MagicMock()
    
    mock_class_query_result(db_mock, [mock_data['test_class']], filter_count=1)
    
    mock_repos['user_repo'].get.return_value = mock_data['test_user']
    mock_repos['room_repo'].get.return_value = mock_data['test_room']

    monday_rule = {'day': 'monday', 'slots': [1, 2]}
    wednesday_rule = {'day': 'wednesday', 'slots': [3, 4]}
    
    # Cần 2 lần gọi thành công
    mock_select_rule.side_effect = [
        (monday_rule, None),      # Mon: Success
        (None, None),             # Tue: Skip
        (wednesday_rule, None),   # Wed: Success
    ] 
    
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date'], prefer_morning=True
    )

    proposal = schedule_service.generate_schedule(db_mock, request)

    assert proposal.successful_sessions == 2
    assert proposal.conflict_count == 0
    assert proposal.statistics['success_rate'] == 100.0 
    assert mock_select_rule.call_count == 3


@patch('app.services.schedule.ScheduleService._find_available_room', return_value=UUID('55555555-5555-5555-5555-555555555555'))
@patch('app.services.schedule.ScheduleService._check_teacher_conflict', return_value=False)
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_conflict_from_request_constraint(
    mock_select_rule, mock_check_teacher_conflict, mock_find_room, schedule_service, mock_repos, mock_data
):
    """(T2) Kiểm tra xung đột cứng từ request (teacher_conflict) được phát hiện đúng."""
    db_mock = MagicMock()
    
    mock_class_query_result(db_mock, [mock_data['test_class']], filter_count=1)
    mock_repos['user_repo'].get.return_value = mock_data['test_user']
    mock_repos['room_repo'].get.return_value = mock_data['test_room']

    rule = {'day': 'monday', 'slots': [1, 2]}
    mock_select_rule.side_effect = [(rule, None)] * 3 + [(None, None)] * 4 

    monday_date_str = str(mock_data['start_date'])
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date'],
        teacher_conflict={
            str(mock_data['teacher_id']): {
                monday_date_str: [1, 2] 
            }
        }
    )

    proposal = schedule_service.generate_schedule(db_mock, request)

    assert proposal.successful_sessions == 2
    assert proposal.conflict_count == 1
    
    conflict = proposal.conflicts[0]
    assert conflict.conflict_type == "request_teacher_conflict"
    assert conflict.session_date == mock_data['start_date']


@patch('app.services.schedule.ScheduleService._attempt_to_schedule_session')
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_max_slots_violation_fixed_rule(
    mock_select_rule, mock_attempt_session, schedule_service, mock_repos, mock_data
):
    """(T3) Kiểm tra ràng buộc max_slots_per_session với quy tắc cố định (dẫn đến HARD EXCEPTION)."""
    db_mock = MagicMock()
    
    fixed_schedule = [{'day': 'monday', 'slots': [1, 2, 3]}]
    test_class_fixed = MockClass(
        id=mock_data['class_id'], teacher_id=mock_data['teacher_id'], 
        max_students=20, sessions_per_week=2, schedule=fixed_schedule, name="Fixed Class"
    )
    
    mock_class_query_result(db_mock, [test_class_fixed], filter_count=1)
    
    conflict_info = ConflictInfo(
        class_id=mock_data['class_id'], class_name="Fixed Class", 
        conflict_type="max_slot_violation", session_date=mock_data['start_date'], 
        time_slots=[1, 2, 3], reason="Fixed rule violates max_slots_per_session limit (2)."
    )
    
    mock_select_rule.side_effect = [
        (None, conflict_info)
    ] + [(None, None)] * 6

    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date'],
        max_slots_per_session=2 
    )

    with pytest.raises(HTTPException) as exc_info:
        schedule_service.generate_schedule(db_mock, request)

    assert exc_info.value.status_code == 409
    assert "Cannot fulfill target of 2 sessions" in exc_info.value.detail


@patch('app.services.schedule.ScheduleService._attempt_to_schedule_session')
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_hard_exception_when_cannot_fulfill_target(
    mock_select_rule, mock_attempt_session, schedule_service, mock_repos, mock_data
):
    """(T4) Kiểm tra ngoại lệ cứng (HTTPException 409) khi không đạt được mục tiêu sessions (Target 9)."""
    db_mock = MagicMock()

    test_class_impossible = MockClass(
        id=mock_data['class_id'], teacher_id=mock_data['teacher_id'], 
        max_students=20, sessions_per_week=10, schedule=[], name="Impossible Class"
    )

    mock_class_query_result(db_mock, [test_class_impossible], filter_count=1)

    target_sessions = 9 
    
    mock_attempt_session.return_value = ConflictInfo(
        class_id=mock_data['class_id'], class_name="Impossible Class", conflict_type="room_unavailable",
        session_date=date(2025, 12, 1), time_slots=[1], reason="No room"
    )
    
    mock_select_rule.return_value = ({'day': 'monday', 'slots': [1, 2]}, None)
    
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date']
    )
    
    with pytest.raises(HTTPException) as exc_info:
        schedule_service.generate_schedule(db_mock, request)

    assert exc_info.value.status_code == 409
    assert f"Cannot fulfill target of {target_sessions} sessions" in exc_info.value.detail


# --------------------------------------------------------------------------
# --- NEW COMPLEX TEST CASES (T5 - T16) ---
# --------------------------------------------------------------------------

@patch('app.services.schedule.ScheduleService._attempt_to_schedule_session')
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_target_calculation_partial_week(mock_select_rule, mock_attempt_session, schedule_service, mock_repos, mock_data):
    """(T5) Kiểm tra tính toán mục tiêu session cho khoảng thời gian lẻ (10 ngày -> Target 3)."""
    db_mock = MagicMock()
    
    end_date = mock_data['start_date'] + timedelta(days=9) # Dec 1 -> Dec 10 (10 days)
    test_class = mock_data['test_class'] # sessions_per_week=2
    
    mock_class_query_result(db_mock, [test_class], filter_count=1)
    
    mock_attempt_session.return_value = SessionProposal(
        class_id=test_class.id, class_name=test_class.name, teacher_id=test_class.teacher_id,
        teacher_name="X", room_id=mock_data['room_id'], room_name="Z", 
        session_date=mock_data['start_date'], time_slots=[1],
        start_time=time(8, 0), end_time=time(9, 30)
    )
    mock_select_rule.side_effect = [({'day': 'monday', 'slots': [1]}, None)] * 3 + [(None, None)] * 7 

    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=end_date
    )

    proposal = schedule_service.generate_schedule(db_mock, request)
    
    assert proposal.successful_sessions == 3
    assert mock_attempt_session.call_count == 3
    assert mock_select_rule.call_count == 3 

@patch('app.services.schedule.ScheduleService._attempt_to_schedule_session')
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_no_schedule_rule_for_the_day(mock_select_rule, mock_attempt_session, schedule_service, mock_repos, mock_data):
    """(T6) Kiểm tra rằng nếu không có quy tắc nào cho ngày (fixed rule), ngày đó bị bỏ qua."""
    db_mock = MagicMock()
    
    fixed_schedule = [{'day': 'sunday', 'slots': [5, 6]}]
    test_class = MockClass(
        id=mock_data['class_id'], teacher_id=mock_data['teacher_id'], 
        max_students=20, sessions_per_week=1, schedule=fixed_schedule, name="Fixed Sunday"
    )
    
    mock_class_query_result(db_mock, [test_class], filter_count=1)
    
    mock_attempt_session.return_value = SessionProposal(
        class_id=test_class.id, class_name="Fixed Sunday", teacher_id=test_class.teacher_id,
        teacher_name="X", room_id=mock_data['room_id'], room_name="Z", 
        session_date=mock_data['end_date'], time_slots=[5, 6],
        start_time=time(18, 0), end_time=time(21, 15)
    )
    
    rule = fixed_schedule[0]
    mock_select_rule.side_effect = [(None, None)] * 6 + [(rule, None)] 
    
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date'] # 7 days
    )

    proposal = schedule_service.generate_schedule(db_mock, request)
    
    assert proposal.successful_sessions == 1
    assert mock_attempt_session.call_count == 1 

@patch('app.services.schedule.ScheduleService._attempt_to_schedule_session')
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_prefer_morning_soft_preference(mock_select_rule, mock_attempt_session, schedule_service, mock_repos, mock_data):
    """(T7) Kiểm tra rằng rule được chọn có ưu tiên buổi sáng (kiểm tra gián tiếp)."""
    db_mock = MagicMock()
    
    test_class = mock_data['test_class']
    mock_class_query_result(db_mock, [test_class], filter_count=1)
    
    morning_rule = {'day': 'monday', 'slots': [1]}
    
    # FIX T7: Set side_effect to ensure 2 calls are successful, and provide 7 total values.
    # The loop runs for 7 days, but should break after the 2nd success.
    mock_select_rule.side_effect = [(morning_rule, None), (morning_rule, None)] + [(None, None)] * 5
    
    mock_attempt_session.return_value = SessionProposal(
        class_id=test_class.id, class_name="Mock 101", teacher_id=test_class.teacher_id,
        teacher_name="X", room_id=mock_data['room_id'], room_name="Z", 
        session_date=mock_data['start_date'], time_slots=morning_rule['slots'],
        start_time=time(8, 0), end_time=time(9, 30)
    )
    
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date'] 
    )

    schedule_service.generate_schedule(db_mock, request)

    # --- robust check: ensure at least one attempt had the morning rule with slots [1]
    called = False
    for call in mock_attempt_session.call_args_list:
        args, kwargs = call
        # rule is positional arg index 3 in _attempt_to_schedule_session signature
        if len(args) > 3:
            rule_arg = args[3]
        else:
            rule_arg = kwargs.get('rule')
        if isinstance(rule_arg, dict) and rule_arg.get('slots') == [1]:
            called = True
            break

    assert called, "Expected at least one _attempt_to_schedule_session call with rule slots [1]"
    assert mock_select_rule.call_count == 2 

@patch('app.services.schedule.ScheduleService._attempt_to_schedule_session')
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_max_slots_violation_on_random_rule(mock_select_rule, mock_attempt_session, schedule_service, mock_repos, mock_data):
    """(T8) Kiểm tra rằng các quy tắc ngẫu nhiên bị loại bỏ nếu chúng vi phạm max_slots_per_session (từ chối 3-slot)."""
    db_mock = MagicMock()
    
    test_class = mock_data['test_class']
    mock_class_query_result(db_mock, [test_class], filter_count=1)
    
    mock_select_rule.return_value = (None, None) 
    mock_attempt_session.assert_not_called()

    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['start_date'], 
        max_slots_per_session=2 
    )
    
    proposal = schedule_service.generate_schedule(db_mock, request)

    assert proposal.successful_sessions == 0
    assert proposal.conflict_count == 0 
    assert mock_attempt_session.call_count == 0

@patch('app.services.schedule.ScheduleService._attempt_to_schedule_session')
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_fixed_rule_on_max_slots_boundary(mock_select_rule, mock_attempt_session, schedule_service, mock_repos, mock_data):
    """(T9) Kiểm tra quy tắc cố định khớp chính xác giới hạn max_slots (không bị từ chối)."""
    db_mock = MagicMock()
    
    fixed_schedule = [{'day': 'monday', 'slots': [1, 2]}]
    test_class_fixed = MockClass(
        id=mock_data['class_id'], teacher_id=mock_data['teacher_id'], 
        max_students=20, sessions_per_week=1, schedule=fixed_schedule, name="Fixed Boundary"
    )
    
    mock_class_query_result(db_mock, [test_class_fixed], filter_count=1)
    
    mock_select_rule.return_value = (fixed_schedule[0], None)
    mock_attempt_session.return_value = SessionProposal(
        class_id=mock_data['class_id'], class_name="Fixed Boundary", teacher_id=mock_data['teacher_id'],
        teacher_name="X", room_id=mock_data['room_id'], room_name="Z", 
        session_date=mock_data['start_date'], time_slots=[1, 2],
        start_time=time(8, 0), end_time=time(11, 15)
    )
    
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date'],
        max_slots_per_session=2 # Boundary match
    )

    proposal = schedule_service.generate_schedule(db_mock, request)
    
    assert proposal.successful_sessions == 1
    assert proposal.conflict_count == 0 
    assert mock_attempt_session.call_count == 1

@patch('app.services.schedule.ScheduleService._attempt_to_schedule_session')
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_multiple_classes_scenario(mock_select_rule, mock_attempt_session, schedule_service, mock_repos, mock_data):
    """(T10) Kiểm tra xử lý nhiều lớp học, với một lớp thành công và một lớp bị xung đột."""
    db_mock = MagicMock()
    
    class_1 = mock_data['test_class'] # Target 2
    class_2 = mock_data['test_class_2'] # Target 1
    
    mock_class_query_result(db_mock, [class_1, class_2], filter_count=2) 

    # FIX T10: Setup side_effect list of objects to return for repo.get (4 attempts total)
    mock_repos['user_repo'].get.side_effect = [
        mock_data['test_user'], mock_data['test_room'], # C1 Mon Lookup 1
        mock_data['test_user'], mock_data['test_room'], # C1 Tue Lookup 2
        mock_data['test_user_2'], mock_data['test_room'], # C2 Mon Lookup 3
        mock_data['test_user_2'], mock_data['test_room'], # C2 Tue Lookup 4
    ]
    
    success_c1 = SessionProposal(
        class_id=class_1.id, class_name=class_1.name, teacher_id=class_1.teacher_id,
        teacher_name=f"{mock_data['test_user'].first_name} {mock_data['test_user'].last_name}", 
        room_id=mock_data['room_id'], room_name="Z", 
        session_date=mock_data['start_date'], time_slots=[1],
        start_time=time(8, 0), end_time=time(9, 30)
    )
    success_c2 = SessionProposal(
        class_id=class_2.id, class_name=class_2.name, teacher_id=class_2.teacher_id,
        teacher_name=f"{mock_data['test_user_2'].first_name} {mock_data['test_user_2'].last_name}", 
        room_id=mock_data['room_id'], room_name="Z", 
        session_date=mock_data['start_date'] + timedelta(days=1), time_slots=[1],
        start_time=time(8, 0), end_time=time(9, 30)
    )
    conflict_c2 = ConflictInfo(
        class_id=class_2.id, class_name=class_2.name, conflict_type="teacher_busy",
        session_date=mock_data['start_date'], time_slots=[1], reason="Teacher is busy."
    )
    
    rule = {'day': 'monday', 'slots': [1]}
    mock_select_rule.return_value = (rule, None) 
    
    # C1 (Mon, Tue) + C2 (Mon, Tue) = 4 calls total to _attempt_to_schedule_session
    mock_attempt_session.side_effect = [
        success_c1,     # C1 Mon (Success 1)
        success_c1,     # C1 Tue (Success 2) 
        conflict_c2,    # C2 Mon (Conflict 1)
        success_c2,     # C2 Tue (Success 1) 
    ]
    
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date'],
        class_ids=[class_1.id, class_2.id]
    )

    proposal = schedule_service.generate_schedule(db_mock, request)
    
    assert proposal.total_classes == 2 
    assert proposal.successful_sessions == 3 
    assert proposal.conflict_count == 1 

@patch('app.services.schedule.ScheduleService._find_available_room', return_value=UUID('55555555-5555-5555-5555-555555555555'))
@patch('app.services.schedule.ScheduleService._check_teacher_conflict', return_value=True) # Forces DB conflict
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_teacher_db_conflict_hard_constraint(
    mock_select_rule, mock_check_teacher_conflict, mock_find_room, schedule_service, mock_repos, mock_data
):
    """(T11) Kiểm tra xung đột với dữ liệu hiện có trong DB (teacher_busy) dẫn đến HARD EXCEPTION."""
    db_mock = MagicMock()
    
    test_class = mock_data['test_class'] # Target 2 sessions
    mock_class_query_result(db_mock, [test_class], filter_count=1)
    
    rule = {'day': 'monday', 'slots': [1, 2]}
    mock_select_rule.return_value = (rule, None)
    
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date']
    )

    with pytest.raises(HTTPException) as exc_info:
        schedule_service.generate_schedule(db_mock, request)
    
    assert exc_info.value.status_code == 409
    assert "Cannot fulfill target of 2 sessions" in exc_info.value.detail


@patch('app.services.schedule.ScheduleService._find_available_room', return_value=None) # Forces Room Unavailable
@patch('app.services.schedule.ScheduleService._check_teacher_conflict', return_value=False)
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_room_db_conflict_hard_constraint(
    mock_select_rule, mock_check_teacher_conflict, mock_find_room, schedule_service, mock_repos, mock_data
):
    """(T12) Kiểm tra xung đột khi không tìm được phòng trống phù hợp (room_unavailable) dẫn đến HARD EXCEPTION."""
    db_mock = MagicMock()
    
    test_class = mock_data['test_class'] # Target 2 sessions
    mock_class_query_result(db_mock, [test_class], filter_count=1)
    
    rule = {'day': 'monday', 'slots': [1, 2]}
    mock_select_rule.return_value = (rule, None)
    
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date']
    )

    with pytest.raises(HTTPException) as exc_info:
        schedule_service.generate_schedule(db_mock, request)
    
    assert exc_info.value.status_code == 409
    assert "Cannot fulfill target of 2 sessions" in exc_info.value.detail

@patch('app.services.schedule.ScheduleService._find_available_room', return_value=UUID('55555555-5555-5555-5555-555555555555'))
@patch('app.services.schedule.ScheduleService._check_teacher_conflict', return_value=False)
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_class_request_conflict_hard_constraint(
    mock_select_rule, mock_check_teacher_conflict, mock_find_room, schedule_service, mock_repos, mock_data
):
    """(T13) Kiểm tra xung đột khi Class bị cấm theo dữ liệu request (class_conflict)."""
    db_mock = MagicMock()
    
    mock_repos['user_repo'].get.return_value = mock_data['test_user']
    mock_repos['room_repo'].get.return_value = mock_data['test_room']
    
    test_class = mock_data['test_class']
    mock_class_query_result(db_mock, [test_class], filter_count=1)
    
    rule = {'day': 'monday', 'slots': [1, 2]}
    mock_select_rule.side_effect = [(rule, None)] * 3 + [(None, None)] * 4 
    
    monday_date_str = str(mock_data['start_date'])
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date'],
        class_conflict={
            str(mock_data['class_id']): {
                monday_date_str: [1, 2] 
            }
        }
    )

    proposal = schedule_service.generate_schedule(db_mock, request)
    
    assert proposal.successful_sessions == 2
    assert proposal.conflict_count == 1
    assert proposal.conflicts[0].conflict_type == "request_class_conflict"

@patch('app.services.schedule.ScheduleService._find_available_room', return_value=UUID('55555555-5555-5555-5555-555555555555'))
@patch('app.services.schedule.ScheduleService._check_teacher_conflict', return_value=False)
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_schedule_two_weeks_full_success(
    mock_select_rule, mock_check_teacher_conflict, mock_find_room, schedule_service, mock_repos, mock_data
):
    """(T14) Kiểm tra lịch kéo dài 2 tuần, đảm bảo target được tính và đạt đủ (Target 4)."""
    db_mock = MagicMock()
    
    test_class = mock_data['test_class'] # 2 sessions/week. Target = 4 sessions.
    mock_class_query_result(db_mock, [test_class], filter_count=1)
    
    mock_repos['user_repo'].get.return_value = mock_data['test_user']
    mock_repos['room_repo'].get.return_value = mock_data['test_room']

    rule = {'day': 'monday', 'slots': [1]}
    mock_select_rule.side_effect = [(rule, None)] * 4 + [(None, None)] * 10 
    
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], 
        end_date=mock_data['end_date'] + timedelta(days=7) # 14 days total
    )

    proposal = schedule_service.generate_schedule(db_mock, request)

    assert proposal.successful_sessions == 4
    assert proposal.conflict_count == 0
    assert mock_select_rule.call_count == 4

@patch('app.services.schedule.ScheduleService._find_available_room', return_value=UUID('55555555-5555-5555-5555-555555555555'))
@patch('app.services.schedule.ScheduleService._check_teacher_conflict', return_value=False)
@patch('app.services.schedule.ScheduleService._select_and_validate_rule')
def test_target_fulfilled_early(
    mock_select_rule, mock_check_teacher_conflict, mock_find_room, schedule_service, mock_repos, mock_data
):
    """(T15) Đảm bảo vòng lặp dừng ngay lập tức khi target sessions được đáp ứng (Target 2)."""
    db_mock = MagicMock()
    
    test_class = mock_data['test_class'] # Target 2 sessions.
    mock_class_query_result(db_mock, [test_class], filter_count=1)
    
    mock_repos['user_repo'].get.return_value = mock_data['test_user']
    mock_repos['room_repo'].get.return_value = mock_data['test_room']

    rule = {'day': 'monday', 'slots': [1, 2]}
    mock_select_rule.side_effect = [(rule, None)] * 2 + [(None, None)] * 5 
    
    request = ScheduleGenerateRequest(
        start_date=mock_data['start_date'], end_date=mock_data['end_date'],
        max_slots_per_session=3 
    )

    proposal = schedule_service.generate_schedule(db_mock, request)

    assert proposal.successful_sessions == 2
    assert proposal.conflict_count == 0
    assert mock_select_rule.call_count == 2 


@patch('app.services.schedule.ScheduleService._find_available_room', return_value=UUID('55555555-5555-5555-5555-555555555555'))
@patch('app.services.schedule.ScheduleService._check_teacher_conflict', return_value=False)
@patch('app.services.schedule.ScheduleService._select_and_validate_rule', return_value=({'day': 'monday', 'slots': [1]}, None))
def test_request_class_id_filter(mock_select_rule, mock_check_teacher_conflict, mock_find_room, schedule_service, mock_repos, mock_data):
    """(T16) Kiểm tra rằng chỉ những class_id được cung cấp trong request mới được xử lý."""
    db_mock = MagicMock()
    
    class_1 = mock_data['test_class'] # Requested, Target 2
    class_2 = mock_data['test_class_2'] # Not requested, Target 1

    mock_class_query_result(db_mock, [class_1], filter_count=2) 
    
    mock_repos['user_repo'].get.return_value = mock_data['test_user']
    mock_repos['room_repo'].get.return_value = mock_data['test_room']

    with patch('app.services.schedule.ScheduleService._attempt_to_schedule_session') as mock_attempt_session:
        mock_attempt_session.side_effect = [
            SessionProposal(
                class_id=class_1.id, class_name="Mock 101", teacher_id=class_1.teacher_id,
                teacher_name=f"{mock_data['test_user'].first_name} {mock_data['test_user'].last_name}",
                room_id=mock_data['room_id'], room_name="Z", 
                session_date=mock_data['start_date'], time_slots=[1], start_time=time(8, 0), end_time=time(9, 30)
            )
        ] * 2

        request = ScheduleGenerateRequest(
            start_date=mock_data['start_date'], end_date=mock_data['end_date'],
            class_ids=[class_1.id] 
        )

        proposal = schedule_service.generate_schedule(db_mock, request)

    assert proposal.total_classes == 1
    assert proposal.successful_sessions == 2
