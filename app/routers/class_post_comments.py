"""
Router: Class Post Comments
Endpoint: /api/v1/classes/{class_id}/posts/{post_id}/comments

Endpoints:
  GET    /                        — Lấy danh sách bình luận (có phân trang)
  POST   /                        — Tạo bình luận mới hoặc reply
  PUT    /{comment_id}            — Chỉnh sửa nội dung bình luận (tác giả only)
  DELETE /{comment_id}            — Xóa mềm bình luận (tác giả / GV / Admin)
"""

from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Any

from app.core.database import get_db
from app.dependencies import get_current_active_user
from app.models.user import User, UserRole
from app.models.academic import Class
from app.models.class_post import ClassPost
from app.repositories.class_post import class_post_repo
from app.repositories.class_post_comment import class_post_comment_repo
from app.schemas.class_post_comment import CommentCreate, CommentUpdate, CommentResponse
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.services import class_post_comment_service
from app.core.route import ResponseWrapperRoute
from app.core.exceptions import APIException

router = APIRouter(
    prefix="/classes",
    tags=["Class Post Comments"],
    route_class=ResponseWrapperRoute,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_class_or_404(db: Session, class_id: UUID) -> Class:
    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise APIException(status_code=404, code="CLASS_NOT_FOUND", message="Lớp học không tồn tại.")
    return class_obj


def _get_active_post_or_404(db: Session, class_id: UUID, post_id: UUID) -> ClassPost:
    post = class_post_repo.get_active_post_by_id(db, post_id=post_id, class_id=class_id)
    if not post:
        raise APIException(status_code=404, code="POST_NOT_FOUND", message="Bài viết không tồn tại hoặc đã bị xóa.")
    return post


def _check_class_access(current_user: User, class_obj: Class) -> None:
    """Kiểm tra user có quyền xem bài viết trong lớp này không."""
    if current_user.role in (UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        return
    user_id_str = str(current_user.id)
    is_staff = (
        str(class_obj.teacher_id) == user_id_str
        or (class_obj.substitute_teacher_id and str(class_obj.substitute_teacher_id) == user_id_str)
        or (class_obj.ta_id and str(class_obj.ta_id) == user_id_str)
    )
    if is_staff:
        return
    is_enrolled = any(str(e.student_id) == user_id_str for e in class_obj.enrollments)
    if not is_enrolled:
        raise APIException(
            status_code=403,
            code="AUTH_PERMISSION_DENIED",
            message="Bạn không có quyền xem bảng tin của lớp học này.",
        )


# ─── GET — Danh sách bình luận ────────────────────────────────────────────────

@router.get(
    "/{class_id}/posts/{post_id}/comments",
    response_model=PaginationResponse[CommentResponse],
)
def get_post_comments(
    class_id: UUID,
    post_id:  UUID,
    page:     int = Query(1, ge=1),
    limit:    int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lấy danh sách top-level bình luận (kèm replies lồng 1 cấp) của 1 bài viết."""
    class_obj = _get_class_or_404(db, class_id)
    _check_class_access(current_user, class_obj)
    _get_active_post_or_404(db, class_id, post_id)

    skip  = (page - 1) * limit
    items = class_post_comment_repo.get_by_post(db, post_id=post_id, skip=skip, limit=limit)
    total = class_post_comment_repo.count_by_post(db, post_id=post_id)

    return PaginationResponse(data=items, total=total, page=page, limit=limit)


# ─── POST — Tạo bình luận ─────────────────────────────────────────────────────

@router.post(
    "/{class_id}/posts/{post_id}/comments",
    response_model=ApiResponse[CommentResponse],
    status_code=201,
)
async def create_post_comment(
    class_id:         UUID,
    post_id:          UUID,
    body:             CommentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Tạo bình luận mới hoặc phản hồi (reply) 1 bình luận trên bài viết.

    - `parent_comment_id = null` → top-level comment
    - `parent_comment_id = <UUID>` → reply (chỉ hỗ trợ lồng 1 cấp)
    """
    class_obj = _get_class_or_404(db, class_id)
    _check_class_access(current_user, class_obj)
    post = _get_active_post_or_404(db, class_id, post_id)

    comment = await class_post_comment_service.create_comment(
        db=db,
        post=post,
        class_obj=class_obj,
        current_user=current_user,
        content=body.content,
        parent_comment_id=body.parent_comment_id,
        background_tasks=background_tasks,
    )

    return ApiResponse(data=comment, message="Đăng bình luận thành công.")


# ─── PUT — Chỉnh sửa bình luận ───────────────────────────────────────────────

@router.put(
    "/{class_id}/posts/{post_id}/comments/{comment_id}",
    response_model=ApiResponse[CommentResponse],
)
def update_post_comment(
    class_id:   UUID,
    post_id:    UUID,
    comment_id: UUID,
    body:       CommentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Chỉnh sửa nội dung bình luận. Chỉ tác giả được phép.

    Sau khi cập nhật, `is_edited` tự động được set thành True.
    """
    class_obj = _get_class_or_404(db, class_id)
    _check_class_access(current_user, class_obj)
    _get_active_post_or_404(db, class_id, post_id)

    comment = class_post_comment_repo.get_active_by_id(db, comment_id=comment_id, post_id=post_id)
    if not comment:
        raise APIException(status_code=404, code="COMMENT_NOT_FOUND", message="Bình luận không tồn tại hoặc đã bị xóa.")

    updated = class_post_comment_service.edit_comment(
        db=db, comment=comment, current_user=current_user, content=body.content
    )
    return ApiResponse(data=updated, message="Chỉnh sửa bình luận thành công.")


# ─── DELETE — Xóa mềm bình luận ─────────────────────────────────────────────

@router.delete(
    "/{class_id}/posts/{post_id}/comments/{comment_id}",
    response_model=ApiResponse[Any],
)
def delete_post_comment(
    class_id:   UUID,
    post_id:    UUID,
    comment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Xóa mềm bình luận (set deleted_at). Dữ liệu không bị xóa khỏi DB.

    Được phép: Tác giả bình luận, GV chủ nhiệm lớp, Quản trị viên.
    """
    class_obj = _get_class_or_404(db, class_id)
    _check_class_access(current_user, class_obj)
    _get_active_post_or_404(db, class_id, post_id)

    comment = class_post_comment_repo.get_active_by_id(db, comment_id=comment_id, post_id=post_id)
    if not comment:
        raise APIException(status_code=404, code="COMMENT_NOT_FOUND", message="Bình luận không tồn tại hoặc đã bị xóa.")

    class_post_comment_service.delete_comment(
        db=db, comment=comment, current_user=current_user, class_obj=class_obj
    )
    return ApiResponse(data={}, message="Xóa bình luận thành công.")
