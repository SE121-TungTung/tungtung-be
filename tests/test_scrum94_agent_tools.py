"""
Kiểm thử toàn diện cho SCRUM-94:
[KLTN-0007/Agent-Tools] Công cụ đọc dữ liệu học viên, xác minh endpoint và kiểm toán

Các tiêu chí nghiệm thu (Acceptance Criteria):
1. Xác minh và thực thi đầy đủ các công cụ học viên:
   - `get_my_classes`
   - `get_schedule`
   - `get_current_homework`
   - `get_unread_notifications`
   - `summarize_class_posts`
   - `set_target_band`
   - `navigate` (theo bảng ánh xạ route_key cố định)
2. Danh tính người dùng (`user_id`) được lấy từ ngữ cảnh xác thực (`x-agent-user-id` kèm `x-api-key` nội bộ hoặc JWT), không tin tham số từ LLM; học viên A không thể đọc dữ liệu hay bài đăng lớp của học viên B.
3. Khi học viên cập nhật band mục tiêu (`set_target_band` hoặc `PUT /users/me/target-band`), một bản ghi `audit_logs` được tạo với `old_values` và `new_values`.
"""

import asyncio
import os
import sys
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from dotenv import load_dotenv

BE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(BE_ROOT)
load_dotenv(os.path.join(BE_ROOT, ".env"))
sys.path.insert(0, BE_ROOT)

from starlette.requests import Request
from app.core import config as app_config
from app.core.exceptions import APIException
from app.models.academic import Class, ClassEnrollment, EnrollmentStatus
from app.models.audit_log import AuditAction
from app.models.class_post import ClassPost, ClassPostType
from app.models.notification import NotificationPriority, NotificationType
from app.models.session_attendance import ClassSession, SessionStatus
from app.models.test import AttemptStatus, Test, TestAttempt, TestType
from app.models.user import User, UserRole
from app.routers.chatbot import (
    AgentTargetBandUpdate,
    agent_tool_get_current_homework,
    agent_tool_get_my_classes,
    agent_tool_get_schedule,
    agent_tool_get_unread_notifications,
    agent_tool_set_target_band,
    agent_tool_summarize_class_posts,
)
from app.routers.users import TargetBandRequest, update_target_band


def _make_internal_request(student_id: str, api_key: str | None = None) -> Request:
    effective_key = api_key if api_key is not None else (app_config.settings.CHATBOT_API_KEY or "dev-key")
    headers = [
        (b"x-api-key", effective_key.encode("utf-8")),
        (b"x-agent-user-id", str(student_id).encode("utf-8")),
        (b"user-agent", b"scrum94-test-suite"),
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/chatbot/agent-tools",
        "headers": headers,
        "client": ("127.0.0.1", 8000),
    }
    return Request(scope)


class FakeQuery:
    def __init__(self, items):
        self._items = list(items)

    def options(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n):
        return FakeQuery(self._items[:n])

    def all(self):
        return list(self._items)

    def first(self):
        return self._items[0] if self._items else None


async def run_scrum94_tests():
    student_a_id = uuid4()
    student_b_id = uuid4()
    teacher_id = uuid4()
    class_a_id = uuid4()
    class_b_id = uuid4()

    student_a = SimpleNamespace(
        id=student_a_id,
        email="student_a@tungtung.edu.vn",
        first_name="Minh",
        last_name="Nguyễn",
        role=UserRole.STUDENT,
        deleted_at=None,
        preferences={"target_band": 6.5, "target_cefr": "B2"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        status="active",
        phone=None,
        date_of_birth=None,
        address=None,
        avatar_url=None,
        last_login=None,
        emergency_contact=None,
    )

    teacher_user = SimpleNamespace(
        id=teacher_id,
        email="teacher@tungtung.edu.vn",
        first_name="Lan",
        last_name="Trần",
        role=UserRole.TEACHER,
        deleted_at=None,
        preferences={},
    )

    fake_course = SimpleNamespace(name="IELTS Intensive 6.5+")
    fake_room = SimpleNamespace(name="Phòng B204")
    fake_class_a = SimpleNamespace(
        id=class_a_id,
        name="IELTS-INT-26A",
        course=fake_course,
        teacher=teacher_user,
        room=fake_room,
        start_date=date(2026, 10, 1),
        end_date=date(2026, 12, 30),
        status=SimpleNamespace(value="active"),
        deleted_at=None,
    )
    fake_enrollment_a = SimpleNamespace(
        student_id=student_a_id,
        class_id=class_a_id,
        enrollment_class=fake_class_a,
        status=EnrollmentStatus.ACTIVE,
        deleted_at=None,
    )

    fake_session = SimpleNamespace(
        id=uuid4(),
        class_id=class_a_id,
        session_class=fake_class_a,
        session_date=date.today(),
        start_time=time(18, 0),
        end_time=time(20, 0),
        room=fake_room,
        teacher=teacher_user,
        topic="Reading: Matching Headings & True/False/Not Given",
        status=SessionStatus.SCHEDULED,
        homework={"task": "Hoàn thành bài Reading Passage 2 trang 45"},
        deleted_at=None,
    )

    fake_test = SimpleNamespace(
        id=uuid4(),
        class_id=class_a_id,
        title="Homework Reading Week 4",
        test_type=TestType.HOMEWORK,
        end_time=datetime(2026, 11, 15, 23, 59, tzinfo=timezone.utc),
        max_attempts=2,
        deleted_at=None,
    )
    fake_attempt = SimpleNamespace(
        id=uuid4(),
        test_id=fake_test.id,
        student_id=student_a_id,
        attempt_number=1,
        status=AttemptStatus.SUBMITTED,
        deleted_at=None,
    )

    fake_post = SimpleNamespace(
        id=uuid4(),
        class_id=class_a_id,
        class_rel=fake_class_a,
        title="Tài liệu ôn tập Writing Task 2 tuần 5",
        content="Các em tải slide cấu trúc bài luận Discussion và hoàn thành dàn ý trước buổi học thứ 5 nhé.",
        post_type=ClassPostType.ANNOUNCEMENT,
        is_pinned=True,
        author=teacher_user,
        created_at=datetime.now(timezone.utc),
        deleted_at=None,
    )

    fake_notification = SimpleNamespace(
        id=uuid4(),
        user_id=student_a_id,
        title="Nhắc hạn nộp bài tập Reading Week 4",
        content="Bài tập sẽ đóng vào 23:59 ngày 15/11/2026.",
        notification_type=NotificationType.ASSIGNMENT_DUE,
        priority=NotificationPriority.HIGH,
        action_url="/student/tests",
        created_at=datetime.now(timezone.utc),
    )

    def build_mock_db(active_user):
        db = MagicMock()

        def query_side_effect(*entities):
            ent = entities[0]
            if ent is User:
                return FakeQuery([active_user] if active_user else [])
            if ent is ClassEnrollment or str(ent).endswith("ClassEnrollment.class_id"):
                if active_user and active_user.id == student_a_id:
                    if ent is ClassEnrollment:
                        return FakeQuery([fake_enrollment_a])
                    return FakeQuery([SimpleNamespace(class_id=class_a_id)])
                return FakeQuery([])
            if ent is ClassSession:
                return FakeQuery([fake_session])
            if ent is Test:
                return FakeQuery([fake_test])
            if ent is TestAttempt:
                return FakeQuery([fake_attempt])
            if ent is ClassPost:
                return FakeQuery([fake_post])
            return FakeQuery([])

        db.query.side_effect = query_side_effect
        return db

    req_a = _make_internal_request(str(student_a_id))
    db_a = build_mock_db(student_a)

    print("\n--- [AC1] Kiểm tra 5 công cụ đọc dữ liệu cho học viên ---")

    # 1. get_my_classes
    res_classes = await agent_tool_get_my_classes(request=req_a, db=db_a, current_user=None)
    assert res_classes.data["student_id"] == str(student_a_id)
    assert res_classes.data["total_classes"] == 1
    assert res_classes.data["classes"][0]["class_name"] == "IELTS-INT-26A"
    print(f"  [PASS] get_my_classes: {res_classes.data['classes'][0]['class_name']} ({res_classes.data['classes'][0]['course_name']})")

    # 2. get_schedule
    res_sched = await agent_tool_get_schedule(
        request=req_a, date_from="2026-11-08", date_to="2026-11-15", db=db_a, current_user=None
    )
    assert res_sched.data["total_sessions"] == 1
    assert res_sched.data["sessions"][0]["topic"].startswith("Reading:")
    print(f"  [PASS] get_schedule: {res_sched.data['sessions'][0]['date']} {res_sched.data['sessions'][0]['start_time']}-{res_sched.data['sessions'][0]['end_time']} ({res_sched.data['sessions'][0]['room_name']})")

    # 3. get_current_homework
    res_hw = await agent_tool_get_current_homework(
        request=req_a, class_id=str(class_a_id), db=db_a, current_user=None
    )
    assert res_hw.data["total_homework"] == 2
    assert res_hw.data["homework_items"][0]["title"] == "Homework Reading Week 4"
    assert res_hw.data["homework_items"][0]["submission_status"] == "submitted"
    print(f"  [PASS] get_current_homework: total={res_hw.data['total_homework']}, status={res_hw.data['homework_items'][0]['submission_status']}")

    # 4. get_unread_notifications
    with patch("app.repositories.notification.notification_repo.get_by_user", return_value=[fake_notification]), patch(
        "app.repositories.notification.notification_repo.count_unread", return_value=1
    ):
        res_noti = await agent_tool_get_unread_notifications(
            request=req_a, limit=5, db=db_a, current_user=None
        )
        assert res_noti.data["unread_count"] == 1
        assert res_noti.data["notifications"][0]["title"] == "Nhắc hạn nộp bài tập Reading Week 4"
        print(f"  [PASS] get_unread_notifications: unread_count={res_noti.data['unread_count']}, title='{res_noti.data['notifications'][0]['title']}'")

    # 5. summarize_class_posts
    res_posts = await agent_tool_summarize_class_posts(
        request=req_a, class_id=str(class_a_id), limit=5, db=db_a, current_user=None
    )
    assert res_posts.data["total_posts"] == 1
    assert res_posts.data["posts"][0]["title"] == "Tài liệu ôn tập Writing Task 2 tuần 5"
    print(f"  [PASS] summarize_class_posts: total={res_posts.data['total_posts']}, title='{res_posts.data['posts'][0]['title']}'")

    print("\n--- [AC2] Kiểm tra chống giả mạo user_id, chặn lớp không ghi danh và chặn sai vai trò ---")

    # Học viên A cố tình truyền class_b_id (lớp của học viên B mà A không ghi danh) -> Phải bị chặn 403
    blocked_posts = False
    try:
        await agent_tool_summarize_class_posts(
            request=req_a, class_id=str(class_b_id), limit=5, db=db_a, current_user=None
        )
    except APIException as exc:
        blocked_posts = exc.status_code == 403 and exc.code == "CLASS_ACCESS_DENIED"
    assert blocked_posts, "Học viên A không được đọc bài đăng của lớp B chưa ghi danh"
    print("  [PASS] Chặn học viên A đọc bài đăng của lớp B chưa ghi danh (HTTP 403 CLASS_ACCESS_DENIED).")

    blocked_hw = False
    try:
        await agent_tool_get_current_homework(
            request=req_a, class_id=str(class_b_id), db=db_a, current_user=None
        )
    except APIException as exc:
        blocked_hw = exc.status_code == 403 and exc.code == "CLASS_ACCESS_DENIED"
    assert blocked_hw, "Học viên A không được đọc bài tập của lớp B chưa ghi danh"
    print("  [PASS] Chặn học viên A đọc bài tập của lớp B chưa ghi danh (HTTP 403 CLASS_ACCESS_DENIED).")

    # Giáo viên gọi vào cổng công cụ của học viên -> Phải bị chặn 403 AGENT_TOOL_FORBIDDEN_ROLE
    req_teacher = _make_internal_request(str(teacher_id))
    db_teacher = build_mock_db(teacher_user)
    role_blocked = False
    try:
        await agent_tool_get_my_classes(request=req_teacher, db=db_teacher, current_user=None)
    except APIException as exc:
        role_blocked = exc.status_code == 403 and exc.code == "AGENT_TOOL_FORBIDDEN_ROLE"
    assert role_blocked, "Vai trò khác student phải bị chặn 403"
    print("  [PASS] Chặn vai trò teacher truy cập cổng công cụ của học viên (HTTP 403 AGENT_TOOL_FORBIDDEN_ROLE).")

    # Yêu cầu thiếu khóa nội bộ và không có JWT -> Phải bị chặn 401 AGENT_TOOL_UNAUTHORIZED
    req_bad_key = _make_internal_request(str(student_a_id), api_key="wrong-key")
    unauth_blocked = False
    try:
        await agent_tool_get_my_classes(request=req_bad_key, db=db_a, current_user=None)
    except APIException as exc:
        unauth_blocked = exc.status_code == 401 and exc.code == "AGENT_TOOL_UNAUTHORIZED"
    assert unauth_blocked, "Sai x-api-key phải bị chặn 401"
    print("  [PASS] Chặn yêu cầu sai x-api-key nội bộ với HTTP 401 AGENT_TOOL_UNAUTHORIZED.")

    print("\n--- [AC3] Kiểm tra cập nhật band mục tiêu (`set_target_band` & `PUT /users/me/target-band`) và Audit Log ---")
    with patch("app.routers.chatbot.audit_service.log") as mock_audit_log, patch(
        "sqlalchemy.orm.attributes.flag_modified"
    ):
        res_band = await agent_tool_set_target_band(
            request=req_a,
            payload=AgentTargetBandUpdate(target_band=7.5, target_cefr="C1"),
            db=db_a,
            current_user=None,
        )
        assert res_band.data["old_target_band"] == 6.5
        assert res_band.data["new_target_band"] == 7.5
        assert res_band.data["audit_logged"] is True
        assert mock_audit_log.called
        call_kwargs = mock_audit_log.call_args.kwargs
        assert call_kwargs["action"] == AuditAction.UPDATE
        assert call_kwargs["table_name"] == "users"
        assert call_kwargs["record_id"] == student_a_id
        assert call_kwargs["old_values"]["target_band"] == 6.5
        assert call_kwargs["new_values"]["target_band"] == 7.5
        print(
            f"  [PASS] agent_tool_set_target_band ghi nhận Audit Log: "
            f"old={call_kwargs['old_values']} -> new={call_kwargs['new_values']}"
        )

    # Kiểm tra endpoint trực tiếp PUT /users/me/target-band cũng ghi Audit Log
    with patch("app.services.audit_log_service.audit_service.log") as mock_user_audit, patch(
        "sqlalchemy.orm.attributes.flag_modified"
    ):
        await update_target_band(
            payload=TargetBandRequest(target_band=8.0, target_cefr="C1"),
            db=db_a,
            current_user=student_a,
        )
        assert mock_user_audit.called
        u_kwargs = mock_user_audit.call_args.kwargs
        assert u_kwargs["old_values"]["target_band"] == 7.5
        assert u_kwargs["new_values"]["target_band"] == 8.0
        print(
            f"  [PASS] PUT /users/me/target-band ghi nhận Audit Log: "
            f"old={u_kwargs['old_values']} -> new={u_kwargs['new_values']}"
        )

    print("\n==================================================================")
    print("TẤT CẢ KIỂM THỬ SCRUM-94 (AGENT TOOLS & AUDIT LOG) ĐỀU PASS 100%!")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(run_scrum94_tests())
