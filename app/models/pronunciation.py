import enum
from sqlalchemy import (
    Column, String, Text, Integer, Numeric, Enum, ForeignKey,
    Index, UniqueConstraint, CheckConstraint, DateTime,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy import func, text
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


class PronunciationPhonemeMastery(BaseModel):
    """
    Theo dõi mức độ thành thạo từng phoneme IPA của mỗi học viên.
    Tích hợp thuật toán SM-2 Spaced Repetition để lên lịch ôn tập.

    mastery_level:
        0 = unseen (chưa luyện bao giờ)
        1 = learning (avg < 50%)
        2 = familiar (50-69%)
        3 = practiced (70-84%)
        4 = mastered (≥ 85%)
    """
    __tablename__ = "pronunciation_phoneme_mastery"
    __table_args__ = (
        UniqueConstraint("student_id", "phoneme", name="uq_phoneme_mastery_student_phoneme"),
        Index("idx_phoneme_mastery_student", "student_id"),
        Index("idx_phoneme_mastery_next_review", "student_id", "next_review_at"),
        CheckConstraint("mastery_level BETWEEN 0 AND 4", name="ck_mastery_level_range"),
    )

    student_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    phoneme = Column(String(10), nullable=False)

    # Mastery tracking
    mastery_level = Column(Integer, default=0, nullable=False)

    # SM-2 Spaced Repetition fields
    repetition_count = Column(Integer, default=0, nullable=False)
    easiness_factor = Column(Numeric(4, 2), default=2.5, nullable=False)
    interval_days = Column(Integer, default=1, nullable=False)
    next_review_at = Column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    # Statistics
    total_attempts = Column(Integer, default=0, nullable=False)
    correct_attempts = Column(Integer, default=0, nullable=False)
    last_score = Column(Numeric(5, 2), nullable=True)
    avg_score_7d = Column(Numeric(5, 2), nullable=True)
    last_practiced_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship
    student = relationship("User", foreign_keys=[student_id])


class PronunciationAssessment(BaseModel):
    """
    Lưu kết quả Placement Test — đánh giá trình độ phát âm ban đầu
    để cá nhân hóa lộ trình luyện tập.
    """
    __tablename__ = "pronunciation_assessments"
    __table_args__ = (
        Index("idx_assessments_student_created", "student_id", "created_at"),
    )

    student_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    cefr_level = Column(String(5), nullable=True)
    ielts_band_estimate = Column(Numeric(3, 1), nullable=True)
    weak_phonemes = Column(JSONB, nullable=False, server_default="[]")
    strong_phonemes = Column(JSONB, nullable=False, server_default="[]")
    assessment_items = Column(JSONB, nullable=True)
    retake_count = Column(Integer, default=0, nullable=False)

    # Relationship
    student = relationship("User", foreign_keys=[student_id])
