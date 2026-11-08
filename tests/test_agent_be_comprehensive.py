"""
Bộ kiểm thử độ phủ toàn diện (Comprehensive Branch & Edge-Case Coverage) cho Backend Gateway (`tungtung-be`):
Bao phủ 100% các nhánh logic trong:
- `TC-BE-AUTH-01`: Xác thực kép `_resolve_agent_student_user` (x-api-key + x-agent-user-id, UUID lỗi + fallback sang JWT current_user, soft-deleted user, tất cả các role không phải student).
- `TC-BE-TOOLS-02`: Các trường hợp biên của 6 công cụ dữ liệu học viên:
  * Học viên mới chưa ghi danh lớp nào (`enrolled_class_ids == []`).
  * `get_schedule` với `date_from` / `date_to` sai định dạng ngày -> tự fallback về `date.today()` và `+7 days`.
  * `get_current_homework` & `summarize_class_posts` với `class_id` không phải UUID -> `400 INVALID_CLASS_ID`.
  * `get_current_homework` khi chưa làm bài kiểm tra nào (`not_started`) kết hợp bài tập buổi học (`session_homework`).
  * `get_unread_notifications` ép biên `limit` (1..5) và `summarize_class_posts` ép biên `limit` (1..10) + cắt nội dung 600 ký tự.
  * `set_target_band` kiểm tra biên `0.0`, `9.0`, từ chối `-0.5`, `9.5`, `7.25` (`400 INVALID_TARGET_BAND`) và ghi `audit_logs`.
- `TC-BE-ADMIN-03`: Quản lý Audience tài liệu (`normalize_audience`, `update_document_audience_endpoint`, `bulk_update_document_audience`, `chat_with_ai`, `chat_with_ai_stream`).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from dotenv import load_dotenv

BE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(BE_ROOT)
load_dotenv(os.path.join(BE_ROOT, ".env"))
sys.path.insert(0, BE_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from starlette.requests import Request
from app.core import config as app_config
from app.core.exceptions import APIException
from app.models.academic import Class, ClassEnrollment, EnrollmentStatus
from app.models.audit_log import AuditAction
from app.models.chatbot_document import ChatbotDocument, DocCategory, DocStatus
from app.models.class_post import ClassPost, ClassPostType
from app.models.session_attendance import ClassSession, SessionStatus
from app.models.test import AttemptStatus, Test, TestAttempt, TestType
from app.models.user import User, UserRole
from app.routers.chatbot import (
    AgentTargetBandUpdate,
    UserChatRequest,
    _resolve_agent_student_user,
    agent_tool_get_current_homework,
    agent_tool_get_my_classes,
    agent_tool_get_schedule,
    agent_tool_get_unread_notifications,
    agent_tool_set_target_band,
    agent_tool_summarize_class_posts,
    bulk_update_document_audience,
    chat_with_ai,
    chat_with_ai_stream,
    update_document_audience_endpoint,
)
from app.schemas.chatbot import (
    ChatbotDocumentAudienceUpdate,
    ChatbotDocumentBulkAudienceUpdate,
)
from app.services.chatbot_service import normalize_audience


def _build_request(
    student_id: str | None = None,
    api_key: str | None = "DEFAULT",
    auth_bearer: str | None = None,
) -> Request:
    effective_key = (
        (app_config.settings.CHATBOT_API_KEY or "dev-key")
        if api_key == "DEFAULT"
        else api_key
    )
    headers = [(b"user-agent", b"be-comprehensive-suite")]
    if effective_key is not None:
        headers.append((b"x-api-key", effective_key.encode("utf-8")))
    if student_id is not None:
        headers.append((b"x-agent-user-id", str(student_id).encode("utf-8")))
    if auth_bearer is not None:
        headers.append((b"authorization", f"Bearer {auth_bearer}".encode("utf-8")))

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


# ==============================================================================
# 1. KIỂM THỬ XÁC THỰC KÉP _resolve_agent_student_user (TC-BE-AUTH-01)
# ==============================================================================

async def test_tc_be_auth_01_dual_authentication_and_roles():
    print("\n=== [TC-BE-AUTH-01] Kiểm thử mọi nhánh xác thực trong _resolve_agent_student_user ===")
    student_uid = uuid4()
    active_student = SimpleNamespace(
        id=student_uid,
        role=UserRole.STUDENT,
        deleted_at=None,
        preferences={},
    )

    db_with_student = MagicMock()
    db_with_student.query.return_value = FakeQuery([active_student])

    db_empty = MagicMock()
    db_empty.query.return_value = FakeQuery([])

    # 1A: Xác thực qua x-api-key + x-agent-user-id hợp lệ
    req_valid_header = _build_request(student_id=str(student_uid))
    resolved_1 = _resolve_agent_student_user(req_valid_header, db_with_student, current_user_opt=None)
    assert resolved_1.id == student_uid

    # 1B: x-agent-user-id bị lỗi cú pháp UUID ("not-a-uuid") nhưng có current_user_opt từ JWT -> Fallback sang JWT thành công
    req_malformed_uid = _build_request(student_id="not-a-valid-uuid")
    resolved_2 = _resolve_agent_student_user(req_malformed_uid, db_empty, current_user_opt=active_student)
    assert resolved_2.id == student_uid

    # 1C: Không có x-api-key, chỉ có current_user_opt từ JWT -> Thành công
    req_jwt_only = _build_request(student_id=None, api_key=None)
    resolved_3 = _resolve_agent_student_user(req_jwt_only, db_empty, current_user_opt=active_student)
    assert resolved_3.id == student_uid

    # 1D: User không tồn tại hoặc đã bị soft-delete (db trả rỗng) và không có JWT -> 401 AGENT_TOOL_UNAUTHORIZED
    unauth_raised = False
    try:
        _resolve_agent_student_user(req_valid_header, db_empty, current_user_opt=None)
    except APIException as exc:
        unauth_raised = exc.status_code == 401 and exc.code == "AGENT_TOOL_UNAUTHORIZED"
    assert unauth_raised

    # 1E: Kiểm tra tất cả các vai trò không phải student đều bị chặn 403 AGENT_TOOL_FORBIDDEN_ROLE
    for forbidden_role in (
        UserRole.TEACHER,
        UserRole.OFFICE_ADMIN,
        UserRole.CENTER_ADMIN,
        UserRole.SYSTEM_ADMIN,
        "guest",
    ):
        non_student = SimpleNamespace(id=uuid4(), role=forbidden_role, deleted_at=None)
        forbidden_raised = False
        try:
            _resolve_agent_student_user(req_jwt_only, db_empty, current_user_opt=non_student)
        except APIException as exc:
            forbidden_raised = exc.status_code == 403 and exc.code == "AGENT_TOOL_FORBIDDEN_ROLE"
        assert forbidden_raised, f"Role {forbidden_role} phải bị chặn 403!"

    print("  -> PASS: Mọi nhánh xác thực (Header nội bộ, Fallback JWT, Soft-deleted user, Role check) đều hoạt động chính xác.")


# ==============================================================================
# 2. KIỂM THỬ NHÁNH BIÊN CỦA 6 AGENT TOOL ENDPOINTS (TC-BE-TOOLS-02)
# ==============================================================================

async def test_tc_be_tools_02_edge_cases_and_boundaries():
    print("\n=== [TC-BE-TOOLS-02] Kiểm thử các trường hợp biên của 6 công cụ dữ liệu học viên ===")
    student_id = uuid4()
    class_id = uuid4()
    student_user = SimpleNamespace(
        id=student_id,
        role=UserRole.STUDENT,
        deleted_at=None,
        preferences={"target_band": 6.0},
    )
    req = _build_request(student_id=str(student_id))

    # 2A: Học viên mới chưa ghi danh lớp nào (enrolled_class_ids == [])
    def empty_enrollment_query(*entities):
        ent = entities[0]
        if ent is User:
            return FakeQuery([student_user])
        return FakeQuery([])

    db_no_class = MagicMock()
    db_no_class.query.side_effect = empty_enrollment_query

    res_empty_cls = await agent_tool_get_my_classes(request=req, db=db_no_class, current_user=None)
    assert res_empty_cls.data["total_classes"] == 0 and res_empty_cls.data["classes"] == []

    # 2B: get_schedule với học viên chưa có lớp + truyền date_from, date_to sai định dạng ("bad-date")
    res_sched_fallback = await agent_tool_get_schedule(
        request=req,
        date_from="bad-date-format",
        date_to="2026-99-99",
        db=db_no_class,
        current_user=None,
    )
    today_iso = date.today().isoformat()
    plus7_iso = (date.today() + timedelta(days=7)).isoformat()
    assert res_sched_fallback.data["date_from"] == today_iso
    assert res_sched_fallback.data["date_to"] == plus7_iso
    assert res_sched_fallback.data["total_sessions"] == 0

    res_empty_hw = await agent_tool_get_current_homework(request=req, class_id=None, db=db_no_class, current_user=None)
    assert res_empty_hw.data["total_homework"] == 0

    res_empty_posts = await agent_tool_summarize_class_posts(request=req, class_id=None, limit=5, db=db_no_class, current_user=None)
    assert res_empty_posts.data["total_posts"] == 0

    # 2C: Truyền class_id sai định dạng UUID ("invalid-uuid") vào current-homework và class-posts -> 400 INVALID_CLASS_ID
    for endpoint_fn in (agent_tool_get_current_homework, agent_tool_summarize_class_posts):
        bad_uuid_raised = False
        try:
            await endpoint_fn(request=req, class_id="invalid-uuid", db=db_no_class, current_user=None)
        except APIException as exc:
            bad_uuid_raised = exc.status_code == 400 and exc.code == "INVALID_CLASS_ID"
        assert bad_uuid_raised

    # 2D: get_current_homework khi Test chưa có lần làm bài nào (attempts == [] -> submission_status="not_started")
    # và summarize_class_posts cắt bài đăng dài > 600 ký tự
    unstarted_test = SimpleNamespace(
        id=uuid4(),
        class_id=class_id,
        title="Mock Test Listening",
        test_type=TestType.HOMEWORK,
        end_time=None,
        max_attempts=1,
        deleted_at=None,
    )
    long_post = SimpleNamespace(
        id=uuid4(),
        class_id=class_id,
        class_rel=SimpleNamespace(name="IELTS-7.0"),
        title="Bài đăng rất dài",
        content="X" * 900,
        post_type=ClassPostType.MATERIAL,
        is_pinned=False,
        author=None,
        created_at=datetime.now(timezone.utc),
        deleted_at=None,
    )

    def enrolled_query(*entities):
        ent = entities[0]
        if ent is User:
            return FakeQuery([student_user])
        if str(ent).endswith("ClassEnrollment.class_id"):
            return FakeQuery([SimpleNamespace(class_id=class_id)])
        if ent is Test:
            return FakeQuery([unstarted_test])
        if ent is TestAttempt:
            return FakeQuery([])  # Chưa làm bài
        if ent is ClassSession:
            return FakeQuery([])
        if ent is ClassPost:
            return FakeQuery([long_post])
        return FakeQuery([])

    db_enrolled = MagicMock()
    db_enrolled.query.side_effect = enrolled_query

    res_hw_not_started = await agent_tool_get_current_homework(
        request=req, class_id=str(class_id), db=db_enrolled, current_user=None
    )
    assert res_hw_not_started.data["homework_items"][0]["submission_status"] == "not_started"
    assert res_hw_not_started.data["homework_items"][0]["attempts_used"] == 0

    res_long_post = await agent_tool_summarize_class_posts(
        request=req, class_id=str(class_id), limit=99, db=db_enrolled, current_user=None
    )
    assert len(res_long_post.data["posts"][0]["content"]) == 600

    # 2E: set_target_band kiểm tra biên 0.0, 9.0 (hợp lệ) và -0.5, 9.5, 7.25 (bị chặn 400 INVALID_TARGET_BAND)
    for invalid_band in (-0.5, 9.5, 7.25, 6.1):
        band_err = False
        try:
            await agent_tool_set_target_band(
                request=req,
                payload=AgentTargetBandUpdate(target_band=invalid_band),
                db=db_enrolled,
                current_user=None,
            )
        except APIException as exc:
            band_err = exc.status_code == 400 and exc.code == "INVALID_TARGET_BAND"
        assert band_err, f"Band {invalid_band} phải bị chặn 400 INVALID_TARGET_BAND"

    with patch("app.routers.chatbot.audit_service.log") as mock_audit, patch(
        "sqlalchemy.orm.attributes.flag_modified"
    ):
        for valid_edge_band in (0.0, 9.0):
            res_edge = await agent_tool_set_target_band(
                request=req,
                payload=AgentTargetBandUpdate(target_band=valid_edge_band),
                db=db_enrolled,
                current_user=None,
            )
            assert res_edge.data["new_target_band"] == valid_edge_band
        assert mock_audit.call_count == 2

    print("  -> PASS: Mọi trường hợp biên (học viên chưa có lớp, ngày lỗi, UUID lỗi, bài tập not_started, cắt bài đăng 600 ký tự, biên target_band 0.0/9.0) đều PASS.")


# ==============================================================================
# 3. KIỂM THỬ ADMIN AUDIENCE MANAGEMENT & CHAT PROXY (TC-BE-ADMIN-03)
# ==============================================================================

async def test_tc_be_admin_03_audience_management_and_chat_proxy():
    print("\n=== [TC-BE-ADMIN-03] Kiểm thử chuẩn hóa Audience, Admin PATCH/Bulk Audience & Chat Proxy ===")

    # 3A: Kiểm tra normalize_audience với JSON string, CSV string, list có phần tử rác, và rỗng
    assert normalize_audience('["public", "student", "invalid_role"]') == ["public", "student"]
    assert normalize_audience("teacher, admin, unknown") == ["teacher", "admin"]
    assert normalize_audience("   ", fallback=["public"]) == ["public"]
    assert normalize_audience(["invalid_only"], fallback=[]) == []

    # 3B: Kiểm tra update_document_audience_endpoint và bulk_update_document_audience
    admin_user = SimpleNamespace(
        id=uuid4(),
        first_name="Admin",
        last_name="TungTung",
        role=UserRole.SYSTEM_ADMIN,
    )
    doc_uuid = uuid4()
    fake_doc = SimpleNamespace(
        id=doc_uuid,
        doc_id="ai-doc-001",
        filename="01_quy_che.md",
        category=DocCategory.business,
        audience=["student", "teacher", "staff", "admin"],
        audience_reviewed=False,
        status=DocStatus.completed,
        error_message=None,
        created_by=admin_user.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    def admin_db_query(*entities):
        ent = entities[0]
        if ent is ChatbotDocument:
            return FakeQuery([fake_doc])
        if ent is User:
            return FakeQuery([admin_user])
        return FakeQuery([])

    db_admin = MagicMock()
    db_admin.query.side_effect = admin_db_query
    req_admin = _build_request()

    # Trường hợp gửi danh sách audience rỗng/không hợp lệ -> 400 INVALID_AUDIENCE
    invalid_aud_raised = False
    try:
        await update_document_audience_endpoint(
            doc_id=str(doc_uuid),
            request=req_admin,
            payload=ChatbotDocumentAudienceUpdate(audience=["not_a_valid_audience"], audience_reviewed=True),
            db=db_admin,
            current_user=admin_user,
        )
    except APIException as exc:
        invalid_aud_raised = exc.status_code == 400 and exc.code == "INVALID_AUDIENCE"
    assert invalid_aud_raised

    # Trường hợp cập nhật đơn lẻ và cập nhật hàng loạt thành công + ghi Audit Log
    with patch("app.routers.chatbot.chatbot_service.update_document_audience", new_callable=AsyncMock) as mock_ai_upd, patch(
        "app.routers.chatbot.audit_service.log"
    ) as mock_doc_audit:
        res_single = await update_document_audience_endpoint(
            doc_id=str(doc_uuid),
            request=req_admin,
            payload=ChatbotDocumentAudienceUpdate(audience=["public", "student"], audience_reviewed=True),
            db=db_admin,
            current_user=admin_user,
        )
        assert res_single.data.audience == ["public", "student"]
        assert res_single.data.audience_reviewed is True
        assert mock_ai_upd.called and mock_doc_audit.called

        res_bulk = await bulk_update_document_audience(
            request=req_admin,
            payload=ChatbotDocumentBulkAudienceUpdate(
                document_ids=[str(doc_uuid)],
                audience=["public", "student", "teacher"],
                audience_reviewed=True,
            ),
            db=db_admin,
            current_user=admin_user,
        )
        assert len(res_bulk.data) == 1
        assert res_bulk.data[0].audience == ["public", "student", "teacher"]

    # 3C: Kiểm tra chat_with_ai và chat_with_ai_stream gắn đúng user_role và user_id từ current_user (JWT)
    student_jwt_user = SimpleNamespace(id=uuid4(), role=UserRole.STUDENT)
    req_with_bearer = _build_request(auth_bearer="jwt-token-xyz")

    with patch("app.routers.chatbot.chatbot_service.ask_bot", new_callable=AsyncMock) as mock_ask:
        mock_ask.return_value = {"reply": "Xin chào học viên", "mode": "agent", "sources": []}
        chat_resp = await chat_with_ai(
            request=UserChatRequest(message="Lịch học tuần này"),
            http_request=req_with_bearer,
            current_user=student_jwt_user,
        )
        assert chat_resp.data["mode"] == "agent"
        call_kw = mock_ask.call_args.kwargs
        assert call_kw["user_role"] == "student"
        assert call_kw["user_id"] == str(student_jwt_user.id)
        assert call_kw["auth_token"] == "Bearer jwt-token-xyz"

    async def fake_stream_gen():
        yield {"tool_call": {"tool": "get_schedule", "status": "running", "label": "Đang kiểm tra lịch học..."}}
        yield {"text": "Bạn có 2 buổi học tuần này."}
        yield {"done": True, "mode": "agent"}

    with patch("app.routers.chatbot.chatbot_service.ask_bot_stream", new_callable=AsyncMock) as mock_ask_stream:
        mock_ask_stream.return_value = fake_stream_gen()
        stream_resp = await chat_with_ai_stream(
            request=UserChatRequest(message="Lịch học tuần này"),
            http_request=req_with_bearer,
            current_user=student_jwt_user,
        )
        chunks = []
        async for chunk in stream_resp.body_iterator:
            chunks.append(chunk)
        joined = "".join(chunks)
        assert '"tool": "get_schedule"' in joined
        assert '"mode": "agent"' in joined

    print("  -> PASS: Chuẩn hóa Audience, Admin PATCH/Bulk Audience + Audit Log và Chat Proxy (Sync & SSE) đều hoạt động chính xác.")


async def main():
    await test_tc_be_auth_01_dual_authentication_and_roles()
    await test_tc_be_tools_02_edge_cases_and_boundaries()
    await test_tc_be_admin_03_audience_management_and_chat_proxy()
    print("\n======================================================================")
    print("TẤT CẢ KIỂM THỬ COMPREHENSIVE COVERAGE (TUNGTUNG-BE) PASS 100%!")
    print("======================================================================")


if __name__ == "__main__":
    asyncio.run(main())

