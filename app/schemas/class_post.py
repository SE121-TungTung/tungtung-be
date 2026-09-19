from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any
from datetime import datetime
from uuid import UUID

from app.models.class_post import ClassPostType, MaterialCategory
from app.schemas.class_post_reaction import ReactionsSummary


# ─── Sub-schemas ─────────────────────────────────────────────────────────────

class AttachmentSchema(BaseModel):
    """Metadata tệp đính kèm Cloudinary."""
    file_name: str
    file_url:  str
    file_size: int
    mime_type: str


class ClassPostAuthorResponse(BaseModel):
    id:         UUID
    full_name:  str
    role:       str
    avatar_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Request Schemas ──────────────────────────────────────────────────────────

class ClassPostUpdate(BaseModel):
    """Schema cập nhật bài viết (tất cả field Optional — PATCH semantics)."""
    title:             Optional[str]              = Field(None, min_length=1, max_length=255)
    content:           Optional[str]              = None
    material_category: Optional[MaterialCategory] = None
    is_comment_locked: Optional[bool]             = None
    # Lưu ý: is_edited KHÔNG cho phép client tự set — Service quản lý


class ClassPostPinRequest(BaseModel):
    """Body cho PATCH /pin endpoint."""
    pin:                bool  = Field(..., description="True = ghim bài, False = bỏ ghim")
    force_unpin_oldest: bool  = Field(
        default=False,
        description="Nếu True và đang đạt giới hạn 3 bài ghim, tự động bỏ ghim bài cũ nhất "
                    "(dùng khi FE user đã xác nhận qua PinLimitModal)",
    )


# ─── Response Schemas ────────────────────────────────────────────────────────

class ClassPostResponse(BaseModel):
    """Response schema cho bài viết lớp học — map 1-1 với ClassPost ORM model."""
    id:                UUID
    class_id:          UUID
    author_id:         UUID
    author:            Optional[ClassPostAuthorResponse] = None

    # Core content
    title:             str
    content:           Optional[str]              = None
    post_type:         ClassPostType
    material_category: Optional[MaterialCategory] = None
    attachments:       List[AttachmentSchema]     = []

    # Lifecycle fields
    is_pinned:         bool
    pinned_at:         Optional[datetime]         = None
    is_comment_locked: bool
    is_edited:         bool

    # Phase 2: Comments & Reactions
    comment_count:     int                       = 0
    reactions_summary: Optional[ReactionsSummary] = None

    # Phase 3: View tracking
    view_count:        int                       = 0

    # Audit fields
    created_at:        datetime
    updated_at:        datetime

    model_config = ConfigDict(from_attributes=True)
