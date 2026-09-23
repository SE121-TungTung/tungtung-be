import enum
from sqlalchemy import Column, String, Text, Integer, Numeric, Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class TargetType(str, enum.Enum):
    WORD = "word"
    PHRASE = "phrase"
    SENTENCE = "sentence"
    IPA = "ipa"


class PronunciationPractice(BaseModel):
    __tablename__ = "pronunciation_practices"
    __table_args__ = (
        Index("idx_pronunciation_practices_student_id", "student_id"),
        Index("idx_pronunciation_practices_student_created", "student_id", "created_at"),
        Index("idx_pronunciation_practices_student_target_type", "student_id", "target_type"),
    )

    student_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_text = Column(String(500), nullable=False)
    target_type = Column(
        Enum(
            TargetType,
            values_callable=lambda obj: [e.value for e in obj],
            native_enum=False,
            name="pronunciation_target_type",
        ),
        nullable=False,
        default=TargetType.WORD,
    )
    target_ipa = Column(String(500), nullable=True)
    actual_ipa = Column(String(500), nullable=True)
    audio_url = Column(Text, nullable=True)
    overall_score = Column(Numeric(5, 2), nullable=False)
    phoneme_results = Column(JSONB, nullable=True)
    component_scores = Column(JSONB, nullable=True)
    error_summary = Column(JSONB, nullable=True)
    feedback_text = Column(Text, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)

    # Relationship
    student = relationship("User", foreign_keys=[student_id], backref="pronunciation_practices")
