"""
Model: ClassPostReaction
Toggle reaction (Like / Heart / Understood) trên bài viết lớp học.

- Bảng giao dịch nhẹ, KHÔNG kế thừa BaseModel (không cần soft-delete).
- Unique constraint: mỗi user chỉ có 1 reaction mỗi loại trên mỗi bài viết.
- Khi "unlike" → DELETE vật lý bản ghi (không soft-delete).
"""

import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, UniqueConstraint, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base


class ReactionType(enum.Enum):
    LIKE       = "like"
    HEART      = "heart"
    UNDERSTOOD = "understood"


class ClassPostReaction(Base):
    """Reaction (Like/Heart/Understood) của 1 user trên 1 bài viết."""

    __tablename__ = "class_post_reactions"

    # ─── PK ──────────────────────────────────────────────────────────────────
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ─── FK ──────────────────────────────────────────────────────────────────
    post_id = Column(
        UUID(as_uuid=True),
        ForeignKey("class_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ─── Data ─────────────────────────────────────────────────────────────────
    # Lưu dạng string (value của enum) thay vì PG native enum để linh hoạt
    reaction_type = Column(String(20), nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ─── Unique constraint ───────────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", "reaction_type", name="uq_reaction_post_user_type"),
    )

    # ─── Relationships ───────────────────────────────────────────────────────
    post = relationship("ClassPost", back_populates="reactions", foreign_keys=[post_id])
    user = relationship("User", foreign_keys=[user_id])
