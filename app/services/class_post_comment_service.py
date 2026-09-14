"""
Service Layer: ClassPostCommentService
Xử lý business logic bình luận Q&A lồng 1 cấp trên bài viết lớp học.

Phân quyền:
  - Tất cả thành viên lớp được bình luận (GV, TA, Admin, Học viên đã ghi danh).
  - Tác giả bình luận được sửa nội dung comment của mình.
  - Tác giả, GV chủ nhiệm, Admin được xóa mềm bình luận.
  - GV / TA / Admin mới được khóa/mở bình luận bài viết.

Notification scope:
  - Top-level comment → notify tác giả bài viết (nếu khác người bình luận).
  - Reply comment → notify tác giả bình luận cha (nếu khác người reply).
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.models.academic import Class
from app.models.class_post import ClassPost
from app.models.class_post_comment import ClassPostComment
from app.models.user import User, UserRole
from app.repositories.class_post_comment import class_post_comment_repo
from app.services.notification_service import run_broadcast_task

logger = logging.getLogger(__name__)


# ─── RBAC Helpers ────────────────────────────────────────────────────────────

def _is_class_member(current_user: User, class_obj: Class) -> bool:
    """Kiểm tra user có phải thành viên lớp không (GV/TA/Admin/Học viên ghi danh)."""
    if current_user.role in (UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        return True
    user_id_str = str(current_user.id)
    is_staff = (
        str(class_obj.teacher_id) == user_id_str
        or (class_obj.substitute_teacher_id and str(class_obj.substitute_teacher_id) == user_id_str)
        or (class_obj.ta_id and str(class_obj.ta_id) == user_id_str)
    )
    if is_staff:
        return True
    return any(str(e.student_id) == user_id_str for e in class_obj.enrollments)


def _is_authorized_to_delete_comment(
    current_user: User,
    comment: ClassPostComment,
    class_obj: Class,
) -> bool:
    """Tác giả comment, GV chủ nhiệm, Admin được xóa bình luận."""
    if current_user.role in (UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        return True
    user_id_str = str(current_user.id)
    if str(comment.author_id) == user_id_str:
        return True
    # GV chủ nhiệm lớp
    return str(class_obj.teacher_id) == user_id_str


# ─── Service Functions ───────────────────────────────────────────────────────

async def create_comment(
    db: Session,
    post: ClassPost,
    class_obj: Class,
    current_user: User,
    content: str,
    parent_comment_id: Optional[UUID],
    background_tasks: BackgroundTasks,
) -> ClassPostComment:
    """Tạo bình luận mới hoặc phản hồi (reply) 1 bình luận.

    Business rules:
      - Kiểm tra `is_comment_locked` → từ chối nếu bài bị khóa.
      - Kiểm tra user là thành viên lớp.
      - Nếu có parent_comment_id, parent phải là top-level (parent.parent_id IS NULL).
      - Sau khi tạo thành công → dispatch notification (background).
    """
    # 1. Kiểm tra khóa bình luận
    if post.is_comment_locked:
        raise APIException(
            status_code=400,
            code="COMMENT_LOCKED",
            message="Bình luận cho bài viết này đã bị khóa bởi giảng viên.",
        )

    # 2. Kiểm tra quyền thành viên
    if not _is_class_member(current_user, class_obj):
        raise APIException(
            status_code=403,
            code="AUTH_PERMISSION_DENIED",
            message="Bạn không có quyền bình luận trong lớp học này.",
        )

    # 3. Kiểm tra nesting limit nếu là reply
    parent_author_id: Optional[UUID] = None
    if parent_comment_id:
        parent = class_post_comment_repo.get_active_by_id(
            db, comment_id=parent_comment_id, post_id=post.id
        )
        if not parent:
            raise APIException(
                status_code=404,
                code="COMMENT_NOT_FOUND",
                message="Bình luận gốc không tồn tại hoặc đã bị xóa.",
            )
        if parent.parent_comment_id is not None:
            # parent là reply → không cho phép lồng cấp 2
            raise APIException(
                status_code=400,
                code="COMMENT_NESTING_LIMIT",
                message="Chỉ hỗ trợ bình luận lồng 1 cấp. Không thể phản hồi trực tiếp vào một phản hồi.",
            )
        parent_author_id = parent.author_id

    # 4. Tạo bình luận
    comment = ClassPostComment(
        post_id=post.id,
        author_id=current_user.id,
        parent_comment_id=parent_comment_id,
        content=content.strip(),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    # 5. Dispatch notification (background, lỗi không ảnh hưởng response)
    try:
        if parent_comment_id and parent_author_id:
            # Reply → notify tác giả comment gốc (nếu khác người reply)
            if str(parent_author_id) != str(current_user.id):
                background_tasks.add_task(
                    run_broadcast_task,
                    user_ids=[parent_author_id],
                    title=f"{current_user.full_name} đã phản hồi bình luận của bạn",
                    content=content[:100],
                    priority="normal",
                    action_url=f"/student/class/{class_obj.id}",
                    channels=["in_app"],
                    notification_type="class_comment_reply",
                )
        else:
            # Top-level → notify tác giả bài viết (nếu khác người bình luận)
            if str(post.author_id) != str(current_user.id):
                background_tasks.add_task(
                    run_broadcast_task,
                    user_ids=[post.author_id],
                    title=f"{current_user.full_name} đã bình luận bài viết của bạn",
                    content=content[:100],
                    priority="normal",
                    action_url=f"/student/class/{class_obj.id}",
                    channels=["in_app"],
                    notification_type="class_post_comment",
                )
    except Exception as exc:
        logger.error(f"Notification dispatch failed for comment {comment.id}: {exc}")

    return comment


def edit_comment(
    db: Session,
    comment: ClassPostComment,
    current_user: User,
    content: str,
) -> ClassPostComment:
    """Chỉnh sửa nội dung bình luận. Chỉ tác giả được phép.

    Tự động gán `is_edited = True` sau khi chỉnh sửa.
    """
    if str(comment.author_id) != str(current_user.id):
        raise APIException(
            status_code=403,
            code="COMMENT_FORBIDDEN",
            message="Chỉ tác giả mới có quyền chỉnh sửa bình luận này.",
        )

    comment.content   = content.strip()
    comment.is_edited = True
    comment.updated_by = current_user.id

    db.commit()
    db.refresh(comment)
    return comment


def delete_comment(
    db: Session,
    comment: ClassPostComment,
    current_user: User,
    class_obj: Class,
) -> None:
    """Xóa mềm bình luận. Tác giả, GV chủ nhiệm, Admin được phép."""
    if not _is_authorized_to_delete_comment(current_user, comment, class_obj):
        raise APIException(
            status_code=403,
            code="COMMENT_FORBIDDEN",
            message="Bạn không có quyền xóa bình luận này.",
        )
    class_post_comment_repo.soft_delete(db, comment=comment, deleted_by_id=current_user.id)
