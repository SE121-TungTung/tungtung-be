"""
Model: ClassPostView
Ghi nhận lượt xem (View Tracking) của học viên trên bài viết lớp học.

- Bảng giao dịch nhẹ, KHÔNG kế thừa BaseModel (không cần soft-delete).
- Unique constraint: mỗi user chỉ có 1 bản ghi view trên 1 bài viết (idempotent).
- viewed_at ghi nhận thời điểm đầu tiên học viên xem bài viết.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, UniqueConstraint, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base


class ClassPostView(Base):
    """Lượt xem bài viết của 1 user (học viên)."""

    __tablename__ = "class_post_views"

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
    viewed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ─── Unique constraint ───────────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_view_post_user"),
    )

    # ─── Relationships ───────────────────────────────────────────────────────
    post = relationship("ClassPost", back_populates="views", foreign_keys=[post_id])
    user = relationship("User", foreign_keys=[user_id])
