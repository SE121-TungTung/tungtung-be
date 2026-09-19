"""
Schema: Class Post Comments (Bình luận Q&A)
Định nghĩa Request và Response schemas cho bình luận trên bài viết lớp học.
"""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ─── Sub-schemas ──────────────────────────────────────────────────────────────

class CommentAuthorResponse(BaseModel):
    """Thông tin tác giả bình luận (rút gọn)."""
    id:         UUID
    full_name:  str
    role:       str
    avatar_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ─── Request Schemas ──────────────────────────────────────────────────────────

class CommentCreate(BaseModel):
    """Body tạo bình luận mới hoặc reply."""
    content:           str           = Field(..., min_length=1, max_length=2000, description="Nội dung bình luận")
    parent_comment_id: Optional[UUID] = Field(None, description="ID bình luận cha — NULL nếu là top-level, UUID nếu là reply")


class CommentUpdate(BaseModel):
    """Body chỉnh sửa nội dung bình luận."""
    content: str = Field(..., min_length=1, max_length=2000, description="Nội dung bình luận đã chỉnh sửa")


# ─── Response Schemas ─────────────────────────────────────────────────────────

class CommentResponse(BaseModel):
    """Response schema cho 1 bình luận (cả top-level và reply)."""
    id:                UUID
    post_id:           UUID
    author_id:         UUID
    author:            Optional[CommentAuthorResponse] = None
    parent_comment_id: Optional[UUID] = None
    content:           str
    is_edited:         bool = False
    created_at:        datetime
    updated_at:        datetime

    # Chỉ hiển thị replies khi là top-level comment
    replies: List[CommentResponse] = []

    model_config = ConfigDict(from_attributes=True)


# Giải quyết forward reference
CommentResponse.model_rebuild()
