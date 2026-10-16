import enum
from sqlalchemy import Column, String, ForeignKey, Index, Enum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy import text
from app.models.base import BaseModel


class WordListSource(str, enum.Enum):
    MANUAL = "manual"
    FLASHCARD = "flashcard"


class PronunciationWordListItem(BaseModel):
    """
    Danh sách từ/câu luyện phát âm cá nhân của học viên.
    Có thể được thêm từ Flashcard (flashcard_id != NULL) hoặc nhập thủ công.
    `text_key` là bản chuẩn hoá (lowercase + strip) dùng để chống trùng lặp và
    đối chiếu với `pronunciation_practices.target_text`.
    """
    __tablename__ = "pronunciation_word_list_items"
    __table_args__ = (
        Index(
            "uq_pron_word_list_student_text",
            "student_id", "text_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("idx_pron_word_list_student", "student_id"),
    )

    student_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_text = Column(String(500), nullable=False)
    text_key = Column(String(500), nullable=False)
    target_type = Column(String(20), nullable=False, default="word")
    ipa = Column(String(200), nullable=True)
    source = Column(
        Enum(
            WordListSource,
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
            name="pronunciation_word_list_source",
        ),
        nullable=False,
        default=WordListSource.MANUAL,
    )
    flashcard_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("flashcards.id", ondelete="SET NULL"),
        nullable=True,
    )

    flashcard = relationship("Flashcard", foreign_keys=[flashcard_id])
