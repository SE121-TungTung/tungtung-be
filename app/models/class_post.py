import enum
from sqlalchemy import Column, String, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel

class ClassPostType(enum.Enum):
    ANNOUNCEMENT = "announcement"
    MATERIAL = "material"

class ClassPost(BaseModel):
    __tablename__ = "class_posts"

    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=True)
    
    post_type = Column(
        Enum(
            ClassPostType,
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
            name="class_post_type"
        ),
        default=ClassPostType.ANNOUNCEMENT,
        nullable=False
    )
    
    # JSONB array of attachments:
    # [{"file_name": "xyz.pdf", "file_url": "https://...", "file_size": 1024, "mime_type": "application/pdf"}]
    attachments = Column(JSONB, default=list, nullable=False)

    # Relationships
    author = relationship("User", foreign_keys=[author_id], backref="class_posts")
    class_rel = relationship("Class", foreign_keys=[class_id], backref="posts")
