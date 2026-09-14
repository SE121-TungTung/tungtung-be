"""
Router: Class Posts
Endpoint: /api/v1/classes/{class_id}/posts

Endpoints:
  POST   /                        — Tạo bài viết mới (có thể kèm file)
  GET    /                        — Lấy danh sách bài viết (filter by post_type)
  PUT    /{post_id}               — Chỉnh sửa bài viết (tác giả / Admin)
  DELETE /{post_id}               — Soft delete bài viết (tác giả / GV / Admin)
  PATCH  /{post_id}/pin           — Ghim / bỏ ghim bài (GV / TA / Admin)
"""

from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional, Any

from app.core.database import get_db
from app.dependencies import get_current_active_user
from app.models.user import User, UserRole
from app.models.academic import Class, EnrollmentStatus
from app.models.class_post import ClassPostType, MaterialCategory
from app.repositories.class_post import class_post_repo
from app.schemas.class_post import ClassPostResponse, ClassPostUpdate, ClassPostPinRequest
from app.schemas.class_post_reaction import ReactionToggleRequest, ReactionToggleResponse
from app.services import class_post_service
from app.services import class_post_reaction_service
from app.services.notification_service import run_broadcast_task
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException

router = APIRouter(
    prefix="/classes",
    tags=["Class Posts"],
    route_class=ResponseWrapperRoute,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_class_or_404(db: Session, class_id: UUID) -> Class:
    class_obj = db.query(Class).filter(Class.id == class_id).first()
    if not class_obj:
        raise APIException(status_code=404, code="CLASS_NOT_FOUND", message="Lớp học không tồn tại.")
    return class_obj


def _check_class_access(current_user: User, class_obj: Class) -> None:
    """Kiểm tra user có quyền xem bài viết lớp này không (GV, TA, Admin, hoặc học viên ghi danh)."""
    if current_user.role in (UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        return
    user_id_str = str(current_user.id)
    is_teacher_or_ta = (
        str(class_obj.teacher_id) == user_id_str
        or (class_obj.substitute_teacher_id and str(class_obj.substitute_teacher_id) == user_id_str)
        or (class_obj.ta_id and str(class_obj.ta_id) == user_id_str)
    )
    if is_teacher_or_ta:
        return
    is_enrolled = any(str(e.student_id) == user_id_str for e in class_obj.enrollments)
    if not is_enrolled:
        raise APIException(
            status_code=403,
            code="AUTH_PERMISSION_DENIED",
            message="Bạn không có quyền xem bảng tin của lớp học này.",
        )


# ─── POST — Tạo bài viết ─────────────────────────────────────────────────────

@router.post("/{class_id}/posts", response_model=ApiResponse[ClassPostResponse], status_code=201)
async def create_class_post(
    class_id: UUID,
    background_tasks: BackgroundTasks,
    title: str = Form(..., min_length=1, max_length=255),
    content: Optional[str] = Form(None),
    post_type: str = Form("announcement"),
    material_category: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Tạo bài viết / tài liệu cho lớp học.

    - Cho phép đính kèm tệp cho cả ANNOUNCEMENT và MATERIAL.
    - Áp dụng upload security policy (MIME, extension, size).
    """
    class_obj = _get_class_or_404(db, class_id)

    # Parse enums
    post_type_enum = ClassPostType.MATERIAL if post_type == "material" else ClassPostType.ANNOUNCEMENT
    mat_cat_enum: Optional[MaterialCategory] = None
    if material_category and post_type_enum == ClassPostType.MATERIAL:
        try:
            mat_cat_enum = MaterialCategory(material_category)
        except ValueError:
            raise APIException(
                status_code=400,
                code="VALIDATION_ERROR",
                message=f"material_category không hợp lệ: '{material_category}'.",
            )

    post = await class_post_service.create_post(
        db=db,
        class_obj=class_obj,
        current_user=current_user,
        title=title,
        content=content,
        post_type=post_type_enum,
        material_category=mat_cat_enum,
        files=files,
    )

    # Gửi notification cho học viên active (background)
    try:
        active_student_ids = [
            enroll.student_id
            for enroll in class_obj.enrollments
            if enroll.status == EnrollmentStatus.ACTIVE and enroll.deleted_at is None
        ]
        if active_student_ids:
            post_type_text = "tài liệu học tập mới" if post_type == "material" else "thông báo mới"
            background_tasks.add_task(
                run_broadcast_task,
                user_ids=active_student_ids,
                title=f"Lớp {class_obj.name} có {post_type_text}",
                content=title,
                priority="normal",
                action_url=f"/student/class/{class_id}",
                channels=["in_app"],
                notification_type="class_announcement",
            )
    except Exception as notif_err:
        # Notification failure không ảnh hưởng tới kết quả tạo bài
        import logging
        logging.getLogger(__name__).error(f"Notification dispatch failed: {notif_err}")

    return ApiResponse(data=post, message="Đăng bài viết thành công.")


# ─── GET — Danh sách bài viết ─────────────────────────────────────────────────

@router.get("/{class_id}/posts", response_model=PaginationResponse[ClassPostResponse])
def get_class_posts(
    class_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    post_type: Optional[str] = Query(None, description="Filter: 'announcement' | 'material'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Lấy danh sách bài viết active của lớp.
    
    - Bài ghim luôn đứng đầu.
    - Hỗ trợ filter theo post_type.
    - Tự lọc bài đã bị soft-delete.
    """
    class_obj = _get_class_or_404(db, class_id)
    _check_class_access(current_user, class_obj)

    post_type_enum: Optional[ClassPostType] = None
    if post_type in ("announcement", "material"):
        post_type_enum = ClassPostType(post_type)

    skip = (page - 1) * limit
    posts = class_post_repo.get_by_class(db, class_id=class_id, skip=skip, limit=limit, post_type=post_type_enum)
    total = class_post_repo.count_by_class(db, class_id=class_id, post_type=post_type_enum)

    return PaginationResponse(data=posts, total=total, page=page, limit=limit)


# ─── PUT — Chỉnh sửa bài viết ────────────────────────────────────────────────

@router.put("/{class_id}/posts/{post_id}", response_model=ApiResponse[ClassPostResponse])
def update_class_post(
    class_id: UUID,
    post_id: UUID,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    material_category: Optional[str] = Form(None),
    is_comment_locked: Optional[bool] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Chỉnh sửa nội dung bài viết. Chỉ tác giả (hoặc Admin) được phép.
    
    Sau khi cập nhật, `is_edited` sẽ tự động được set thành True.
    """
    post = class_post_repo.get_active_post_by_id(db, post_id=post_id, class_id=class_id)
    if not post:
        raise APIException(status_code=404, code="POST_NOT_FOUND", message="Bài viết không tồn tại hoặc đã bị xóa.")

    mat_cat_enum: Optional[MaterialCategory] = None
    if material_category:
        try:
            mat_cat_enum = MaterialCategory(material_category)
        except ValueError:
            raise APIException(
                status_code=400,
                code="VALIDATION_ERROR",
                message=f"material_category không hợp lệ: '{material_category}'.",
            )

    updated_post = class_post_service.update_post(
        db=db,
        post=post,
        current_user=current_user,
        title=title,
        content=content,
        material_category=mat_cat_enum,
        is_comment_locked=is_comment_locked,
    )
    return ApiResponse(data=updated_post, message="Cập nhật bài viết thành công.")


# ─── DELETE — Soft delete bài viết ───────────────────────────────────────────

@router.delete("/{class_id}/posts/{post_id}", response_model=ApiResponse[Any])
def delete_class_post(
    class_id: UUID,
    post_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Xóa mềm bài viết (set deleted_at + deleted_by). Dữ liệu không bị xóa khỏi DB."""
    class_obj = _get_class_or_404(db, class_id)

    post = class_post_repo.get_active_post_by_id(db, post_id=post_id, class_id=class_id)
    if not post:
        raise APIException(status_code=404, code="POST_NOT_FOUND", message="Bài viết không tồn tại hoặc đã bị xóa.")

    class_post_service.soft_delete_post(db=db, post=post, current_user=current_user, class_obj=class_obj)
    return ApiResponse(data={}, message="Xóa bài viết thành công.")


# ─── PATCH /pin — Ghim / bỏ ghim bài ────────────────────────────────────────

@router.patch("/{class_id}/posts/{post_id}/pin", response_model=ApiResponse[ClassPostResponse])
def pin_class_post(
    class_id: UUID,
    post_id: UUID,
    body: ClassPostPinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Ghim hoặc bỏ ghim bài viết. Chỉ GV / TA / Admin của lớp được phép.

    Giới hạn ghim: **tối đa 3 bài / lớp**.

    Khi đạt giới hạn mà `force_unpin_oldest = False`:
    - Trả về 409 POST_PIN_LIMIT_EXCEEDED kèm `oldest_pinned_id` trong details.
    - FE hiển thị PinLimitModal cho user xác nhận.

    Khi user xác nhận trong modal → FE gọi lại với `force_unpin_oldest = True`:
    - Bài ghim cũ nhất tự động bị bỏ ghim.
    - Bài hiện tại được ghim.
    """
    class_obj = _get_class_or_404(db, class_id)

    post = class_post_repo.get_active_post_by_id(db, post_id=post_id, class_id=class_id)
    if not post:
        raise APIException(status_code=404, code="POST_NOT_FOUND", message="Bài viết không tồn tại hoặc đã bị xóa.")

    updated_post = class_post_service.toggle_pin(
        db=db,
        class_id=class_id,
        post=post,
        current_user=current_user,
        class_obj=class_obj,
        pin=body.pin,
        force_unpin_oldest=body.force_unpin_oldest,
    )
    action = "Ghim" if body.pin else "Bỏ ghim"
    return ApiResponse(data=updated_post, message=f"{action} bài viết thành công.")


# ─── POST /reactions — Toggle reaction ───────────────────────────────────────

@router.post("/{class_id}/posts/{post_id}/reactions", response_model=ApiResponse[ReactionToggleResponse])
def toggle_post_reaction(
    class_id: UUID,
    post_id:  UUID,
    body:     ReactionToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Toggle reaction (Like / Heart / Understood) trên bài viết.

    - Click lần 1 → thêm reaction.
    - Click lần 2 (cùng type) → bỏ reaction.
    - 1 user có thể active nhiều type cùng lúc trên cùng bài viết.
    """
    class_obj = _get_class_or_404(db, class_id)
    _check_class_access(current_user, class_obj)

    post = class_post_repo.get_active_post_by_id(db, post_id=post_id, class_id=class_id)
    if not post:
        raise APIException(status_code=404, code="POST_NOT_FOUND", message="Bài viết không tồn tại hoặc đã bị xóa.")

    result = class_post_reaction_service.toggle_reaction(
        db=db,
        post=post,
        user_id=current_user.id,
        reaction_type=body.reaction_type,
    )
    action_text = "Đã thêm" if result.action == "added" else "Đã bỏ"
    return ApiResponse(data=result, message=f"{action_text} reaction '{body.reaction_type}'.")


# ─── PATCH /lock-comments — Khóa / Mở bình luận ─────────────────────────────

class _LockCommentsBody(ClassPostUpdate):
    pass  # Tái dùng ClassPostUpdate nhưng chỉ cần is_comment_locked


from pydantic import BaseModel as PydanticBaseModel

class LockCommentsRequest(PydanticBaseModel):
    is_comment_locked: bool


@router.patch("/{class_id}/posts/{post_id}/lock-comments", response_model=ApiResponse[ClassPostResponse])
def lock_post_comments(
    class_id: UUID,
    post_id:  UUID,
    body:     LockCommentsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Bật / tắt khóa bình luận cho 1 bài viết.

    Khi khóa: Học viên không thể đăng bình luận mới.
    Quyền hạn: Chỉ Giáo viên / Trợ giảng / Quản trị viên.
    """
    class_obj = _get_class_or_404(db, class_id)

    # Chỉ staff/admin mới được khóa
    user_id_str = str(current_user.id)
    is_staff = (
        current_user.role in (UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN)
        or str(class_obj.teacher_id) == user_id_str
        or (class_obj.substitute_teacher_id and str(class_obj.substitute_teacher_id) == user_id_str)
        or (class_obj.ta_id and str(class_obj.ta_id) == user_id_str)
    )
    if not is_staff:
        raise APIException(
            status_code=403,
            code="AUTH_PERMISSION_DENIED",
            message="Chỉ Giáo viên / Trợ giảng / Quản trị viên mới có quyền khóa bình luận.",
        )

    post = class_post_repo.get_active_post_by_id(db, post_id=post_id, class_id=class_id)
    if not post:
        raise APIException(status_code=404, code="POST_NOT_FOUND", message="Bài viết không tồn tại hoặc đã bị xóa.")

    post.is_comment_locked = body.is_comment_locked
    post.updated_by = current_user.id
    db.commit()
    db.refresh(post)

    state = "Khóa" if body.is_comment_locked else "Mở khóa"
    return ApiResponse(data=post, message=f"{state} bình luận bài viết thành công.")

