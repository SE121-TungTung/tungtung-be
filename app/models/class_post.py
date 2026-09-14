import enum
from sqlalchemy import Column, String, Text, ForeignKey, Enum, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy import DateTime
from app.models.base import BaseModel


# ===========================
# ENUMERATIONS
# ===========================

class ClassPostType(enum.Enum):
    ANNOUNCEMENT = "announcement"
    MATERIAL = "material"


class MaterialCategory(enum.Enum):
    LECTURE_SLIDE = "lecture_slide"
    EXERCISE      = "exercise"
    REFERENCE     = "reference"
    AUDIO         = "audio"
    VIDEO         = "video"
    OTHER         = "other"


# ===========================
# MODEL
# ===========================

class ClassPost(BaseModel):
    """Bài đăng bảng tin lớp học (Thông báo hoặc Tài liệu).
    
    Kế thừa BaseModel — có sẵn: id (UUID PK), created_at, updated_at,
    deleted_at (soft delete), created_by, updated_by.
    """
    __tablename__ = "class_posts"

    # Foreign keys
    class_id  = Column(UUID(as_uuid=True), ForeignKey("classes.id",  ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id",    ondelete="CASCADE"), nullable=False, index=True)

    # Core content
    title   = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)

    # Post type
    post_type = Column(
        Enum(
            ClassPostType,
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
            name="class_post_type",
        ),
        default=ClassPostType.ANNOUNCEMENT,
        nullable=False,
    )

    # Material metadata — chỉ có nghĩa khi post_type = MATERIAL
    material_category = Column(
        Enum(
            MaterialCategory,
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
            name="material_category",
        ),
        nullable=True,
    )

    # JSONB array of attachments:
    # [{"file_name": "xyz.pdf", "file_url": "https://...", "file_size": 1024, "mime_type": "application/pdf"}]
    attachments = Column(JSONB, default=list, nullable=False)

    # ─── Lifecycle / vòng đời bài viết ─────────────────────────────────────
    # Ghim bài (tối đa 3 bài/lớp)
    is_pinned = Column(Boolean, default=False, nullable=False)
    pinned_at = Column(DateTime(timezone=True), nullable=True)

    # Trạng thái bổ sung
    is_comment_locked = Column(Boolean, default=False, nullable=False)
    is_edited         = Column(Boolean, default=False, nullable=False)

    # Soft-delete metadata — ai đã xóa bài này
    deleted_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ─── Relationships ──────────────────────────────────────────────────────
    author    = relationship("User",  foreign_keys=[author_id],  backref="class_posts")
    class_rel = relationship("Class", foreign_keys=[class_id],   backref="posts")
    deleter   = relationship("User",  foreign_keys=[deleted_by])

    # Phase 2 relationships
    comments  = relationship(
        "ClassPostComment",
        back_populates="post",
        foreign_keys="ClassPostComment.post_id",
        primaryjoin="and_(ClassPostComment.post_id==ClassPost.id, ClassPostComment.deleted_at==None, ClassPostComment.parent_comment_id==None)",
        order_by="ClassPostComment.created_at.asc()",
    )
    reactions = relationship(
        "ClassPostReaction",
        back_populates="post",
        foreign_keys="ClassPostReaction.post_id",
    )

