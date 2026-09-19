"""
Model: ClassPostDownload
Ghi nhận lượt tải tệp đính kèm bài viết lớp học của học viên.

- Bảng giao dịch nhẹ, KHÔNG kế thừa BaseModel (không cần soft-delete).
- Unique constraint: (post_id, user_id, file_name) để đảm bảo tính idempotent (ghi nhận lần tải đầu tiên của từng file).
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, UniqueConstraint, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base


class ClassPostDownload(Base):
    """Lượt tải tệp đính kèm bài viết của học viên."""

    __tablename__ = "class_post_downloads"

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
    file_name = Column(String(255), nullable=False)
    file_url = Column(Text, nullable=True)

    downloaded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ─── Unique constraint ───────────────────────────────────────────────────
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", "file_name", name="uq_download_post_user_file"),
    )

    # ─── Relationships ───────────────────────────────────────────────────────
    post = relationship("ClassPost", foreign_keys=[post_id])
    user = relationship("User", foreign_keys=[user_id])
