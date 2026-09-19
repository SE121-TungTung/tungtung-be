"""
Model: ClassPostComment
Bình luận Q&A lồng 1 cấp trên bài viết lớp học.

- top-level comment: parent_comment_id IS NULL
- reply (cấp 1): parent_comment_id trỏ đến 1 top-level comment
- Hệ thống KHÔNG cho phép lồng cấp 2 (được enforce tại service layer).
"""

import uuid
from sqlalchemy import Column, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class ClassPostComment(BaseModel):
    """Bình luận trên bài viết lớp học (lồng tối đa 1 cấp)."""

    __tablename__ = "class_post_comments"

    # ─── FK ─────────────────────────────────────────────────────────────────
    post_id = Column(
        UUID(as_uuid=True),
        ForeignKey("class_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    author_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # NULL = top-level, non-NULL = reply (chỉ lồng 1 cấp)
    parent_comment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("class_post_comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # ─── Content ─────────────────────────────────────────────────────────────
    content   = Column(Text, nullable=False)
    is_edited = Column(Boolean, default=False, nullable=False)

    # ─── Relationships ───────────────────────────────────────────────────────
    author = relationship("User", foreign_keys=[author_id])
    post   = relationship("ClassPost", back_populates="comments", foreign_keys=[post_id])

    # Self-referential: parent → top-level comment, replies → list of replies
    parent  = relationship(
        "ClassPostComment",
        remote_side="ClassPostComment.id",
        foreign_keys=[parent_comment_id],
        back_populates="replies",
    )
    replies = relationship(
        "ClassPostComment",
        foreign_keys=[parent_comment_id],
        back_populates="parent",
        primaryjoin="and_(ClassPostComment.parent_comment_id==ClassPostComment.id, ClassPostComment.deleted_at==None)",
        order_by="ClassPostComment.created_at.asc()",
    )
