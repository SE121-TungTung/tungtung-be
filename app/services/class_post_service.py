"""
Service Layer: ClassPostService
Xử lý toàn bộ business logic bài viết lớp học.

Các trách nhiệm:
  - Upload security (MIME whitelist, extension blocklist, size limit)
  - Tạo / cập nhật / soft-delete bài viết
  - Ghim / bỏ ghim bài (enforce giới hạn 3 bài/lớp)
"""

import os
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.models.academic import Class
from app.models.class_post import ClassPost, ClassPostType, MaterialCategory
from app.models.user import User, UserRole
from app.repositories.class_post import class_post_repo
from app.services.cloudinary import handle_cloudinary_upload

logger = logging.getLogger(__name__)

# ─── Upload Security Policy ─────────────────────────────────────────────────

MIME_WHITELIST: set[str] = {
    # Tài liệu văn phòng
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Hình ảnh
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    # Audio
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
    "audio/mp4",
    "audio/x-m4a",
}

BLOCKED_EXTENSIONS: set[str] = {
    ".exe", ".sh", ".bat", ".cmd",
    ".js", ".mjs", ".ts",
    ".py", ".rb", ".php", ".pl",
    ".vbs", ".ps1", ".psm1", ".psd1",
    ".dll", ".so", ".dylib",
}

AUDIO_MIME_PREFIXES = {"audio/"}

MAX_SIZE_DOC_IMAGE: int = 25 * 1024 * 1024  # 25 MB
MAX_SIZE_AUDIO: int     = 50 * 1024 * 1024  # 50 MB
MAX_FILES_PER_POST: int = 5
PIN_LIMIT_PER_CLASS: int = 3


# ─── Helpers ────────────────────────────────────────────────────────────────

def _is_authorized_to_post(current_user: User, class_obj: Class) -> bool:
    """Kiểm tra user có quyền đăng bài trong lớp không."""
    if current_user.role in (UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        return True
    user_id_str = str(current_user.id)
    return (
        str(class_obj.teacher_id) == user_id_str
        or (class_obj.substitute_teacher_id and str(class_obj.substitute_teacher_id) == user_id_str)
        or (class_obj.ta_id and str(class_obj.ta_id) == user_id_str)
    )


def _is_authorized_to_pin(current_user: User, class_obj: Class) -> bool:
    """GV / TA / Admin của lớp mới được ghim bài."""
    return _is_authorized_to_post(current_user, class_obj)


def _is_authorized_to_delete(current_user: User, post: ClassPost, class_obj: Class) -> bool:
    """Tác giả, teacher lớp, hoặc Admin mới được xóa bài."""
    if current_user.role in (UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        return True
    user_id_str = str(current_user.id)
    return (
        str(post.author_id) == user_id_str
        or str(class_obj.teacher_id) == user_id_str
        or (class_obj.substitute_teacher_id and str(class_obj.substitute_teacher_id) == user_id_str)
    )


def _is_authorized_to_edit(current_user: User, post: ClassPost) -> bool:
    """Chỉ tác giả mới được chỉnh sửa nội dung bài viết."""
    if current_user.role in (UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        return True
    return str(post.author_id) == str(current_user.id)


async def _validate_and_upload_files(files: List[UploadFile]) -> List[dict]:
    """Kiểm tra upload security policy và upload lên Cloudinary.

    Returns:
        List attachment dicts: [{file_name, file_url, file_size, mime_type}]

    Raises:
        APIException 400: UPLOAD_TOO_MANY_FILES | UPLOAD_BLOCKED_EXTENSION |
                          UPLOAD_INVALID_MIME   | UPLOAD_FILE_TOO_LARGE
    """
    # Lọc file rỗng (browser có thể gửi thêm 1 UploadFile rỗng)
    valid_files = [f for f in files if f.filename]

    if len(valid_files) > MAX_FILES_PER_POST:
        raise APIException(
            status_code=400,
            code="UPLOAD_TOO_MANY_FILES",
            message=f"Chỉ cho phép tối đa {MAX_FILES_PER_POST} tệp mỗi bài viết.",
        )

    attachments: List[dict] = []

    for file in valid_files:
        # 1. Kiểm tra phần mở rộng bị chặn
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext in BLOCKED_EXTENSIONS:
            raise APIException(
                status_code=400,
                code="UPLOAD_BLOCKED_EXTENSION",
                message=f"Định dạng tệp '{ext}' bị cấm vì lý do bảo mật.",
            )

        # 2. Kiểm tra MIME type whitelist
        mime = (file.content_type or "").lower()
        if mime not in MIME_WHITELIST:
            raise APIException(
                status_code=400,
                code="UPLOAD_INVALID_MIME",
                message=f"Loại MIME '{mime}' không được hỗ trợ. Chỉ chấp nhận tài liệu, hình ảnh và audio.",
            )

        # 3. Đọc bytes để kiểm tra kích thước thực
        content = await file.read()
        file_size = len(content)

        is_audio = any(mime.startswith(p) for p in AUDIO_MIME_PREFIXES)
        max_size = MAX_SIZE_AUDIO if is_audio else MAX_SIZE_DOC_IMAGE

        if file_size > max_size:
            limit_mb = max_size // (1024 * 1024)
            raise APIException(
                status_code=400,
                code="UPLOAD_FILE_TOO_LARGE",
                message=f"Tệp '{file.filename}' vượt quá giới hạn {limit_mb}MB.",
            )

        # 4. Đặt lại con trỏ đọc và upload Cloudinary
        await file.seek(0)
        try:
            result = await handle_cloudinary_upload(file, folder_name="class_materials")
        except Exception as exc:
            logger.error(f"Cloudinary upload failed for {file.filename}: {exc}")
            raise APIException(
                status_code=500,
                code="UPLOAD_FAILED",
                message=f"Không thể tải tệp '{file.filename}' lên hệ thống. Vui lòng thử lại.",
            )

        attachments.append({
            "file_name": file.filename,
            "file_url":  result["file_url"],
            "file_size": result["bytes"],
            "mime_type": mime,
        })

    return attachments


# ─── Service Functions ───────────────────────────────────────────────────────

async def create_post(
    db: Session,
    class_obj: Class,
    current_user: User,
    title: str,
    content: Optional[str],
    post_type: ClassPostType,
    material_category: Optional[MaterialCategory],
    files: Optional[List[UploadFile]],
) -> ClassPost:
    """Tạo bài viết mới. Xử lý upload file cho cả ANNOUNCEMENT và MATERIAL."""
    if not _is_authorized_to_post(current_user, class_obj):
        raise APIException(
            status_code=403,
            code="POST_FORBIDDEN",
            message="Bạn không có quyền đăng bài trong lớp này.",
        )

    # Upload file (cả 2 loại bài đều được đính kèm)
    attachments: List[dict] = []
    if files:
        attachments = await _validate_and_upload_files(files)

    post = ClassPost(
        class_id=class_obj.id,
        author_id=current_user.id,
        title=title.strip(),
        content=content,
        post_type=post_type,
        material_category=material_category,
        attachments=attachments,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


async def update_post(
    db: Session,
    post: ClassPost,
    current_user: User,
    title: Optional[str] = None,
    content: Optional[str] = None,
    material_category: Optional[MaterialCategory] = None,
    is_comment_locked: Optional[bool] = None,
    remove_attachment_indices: Optional[List[int]] = None,
    new_files: Optional[List[UploadFile]] = None,
) -> ClassPost:
    """Chỉnh sửa nội dung bài viết. Chỉ tác giả (hoặc Admin) được phép.

    Hỗ trợ quản lý tệp đính kèm:
    - remove_attachment_indices: danh sách index (0-based) của attachments cần xóa
    - new_files: danh sách file mới cần upload và thêm vào
    """
    if not _is_authorized_to_edit(current_user, post):
        raise APIException(
            status_code=403,
            code="POST_FORBIDDEN",
            message="Chỉ tác giả mới có quyền chỉnh sửa bài viết này.",
        )

    if title is not None:
        post.title = title.strip()
    if content is not None:
        post.content = content
    if material_category is not None:
        post.material_category = material_category
    if is_comment_locked is not None:
        post.is_comment_locked = is_comment_locked

    # ─── Xử lý attachments ────────────────────────────────────────────────
    current_attachments = list(post.attachments or [])

    # 1. Xóa attachments theo index (giảm dần để index không bị lệch)
    if remove_attachment_indices:
        valid_indices = sorted(
            [i for i in remove_attachment_indices if 0 <= i < len(current_attachments)],
            reverse=True,
        )
        for idx in valid_indices:
            current_attachments.pop(idx)

    # 2. Upload file mới
    new_attachments: List[dict] = []
    if new_files:
        new_attachments = await _validate_and_upload_files(new_files)

    # 3. Merge và kiểm tra giới hạn
    merged = current_attachments + new_attachments
    if len(merged) > MAX_FILES_PER_POST:
        raise APIException(
            status_code=400,
            code="UPLOAD_TOO_MANY_FILES",
            message=f"Tổng số tệp đính kèm không được vượt quá {MAX_FILES_PER_POST}. "
                    f"Hiện tại: {len(current_attachments)} giữ lại + {len(new_attachments)} mới = {len(merged)}.",
        )

    # Chỉ cập nhật attachments nếu có thay đổi
    if remove_attachment_indices or new_files:
        post.attachments = merged

    post.is_edited = True
    post.updated_by = current_user.id

    db.commit()
    db.refresh(post)
    return post


def soft_delete_post(
    db: Session,
    post: ClassPost,
    current_user: User,
    class_obj: Class,
) -> None:
    """Soft delete bài viết — set deleted_at + deleted_by, KHÔNG xóa khỏi DB."""
    if not _is_authorized_to_delete(current_user, post, class_obj):
        raise APIException(
            status_code=403,
            code="POST_FORBIDDEN",
            message="Bạn không có quyền xóa bài viết này.",
        )

    now = datetime.now(timezone.utc)
    post.deleted_at = now
    post.deleted_by = current_user.id
    post.updated_by = current_user.id

    # Nếu bài đang ghim thì tự động bỏ ghim
    if post.is_pinned:
        post.is_pinned = False
        post.pinned_at = None

    db.commit()


def toggle_pin(
    db: Session,
    class_id: UUID,
    post: ClassPost,
    current_user: User,
    class_obj: Class,
    pin: bool,
    force_unpin_oldest: bool = False,
) -> ClassPost:
    """Ghim hoặc bỏ ghim bài viết.

    Args:
        force_unpin_oldest: Nếu True và đang ở giới hạn 3, tự động bỏ ghim
            bài ghim cũ nhất rồi ghim bài hiện tại (khi FE user đã confirm).

    Raises:
        APIException 409 POST_PIN_LIMIT_EXCEEDED: Khi đạt giới hạn và
            force_unpin_oldest=False. Response details chứa oldest_pinned_id
            để FE hiển thị PinLimitModal.
    """
    if not _is_authorized_to_pin(current_user, class_obj):
        raise APIException(
            status_code=403,
            code="POST_FORBIDDEN",
            message="Chỉ giáo viên / trợ giảng / admin mới được ghim bài.",
        )

    if pin:
        pinned_count = class_post_repo.get_pinned_count(db, class_id)
        already_pinned = post.is_pinned  # Ghim lại bài đang ghim → no-op

        if not already_pinned and pinned_count >= PIN_LIMIT_PER_CLASS:
            if not force_unpin_oldest:
                # Trả về thông tin bài ghim cũ nhất để FE hiển thị modal
                oldest = class_post_repo.get_oldest_pinned(db, class_id)
                raise APIException(
                    status_code=409,
                    code="POST_PIN_LIMIT_EXCEEDED",
                    message=f"Lớp đã có {PIN_LIMIT_PER_CLASS} bài ghim. "
                            "Gỡ bỏ 1 bài ghim cũ trước khi ghim bài mới.",
                    details={
                        "oldest_pinned_id":    str(oldest.id) if oldest else None,
                        "oldest_pinned_title": oldest.title  if oldest else None,
                    },
                )
            else:
                # User đã confirm → unpin bài cũ nhất
                oldest = class_post_repo.get_oldest_pinned(db, class_id)
                if oldest:
                    oldest.is_pinned = False
                    oldest.pinned_at = None
                    oldest.updated_by = current_user.id

        post.is_pinned = True
        post.pinned_at = datetime.now(timezone.utc)
    else:
        post.is_pinned = False
        post.pinned_at = None

    post.updated_by = current_user.id
    db.commit()
    db.refresh(post)
    return post
