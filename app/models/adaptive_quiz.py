import enum
from sqlalchemy import (
    Column, String, Integer, Numeric, Boolean, DateTime,
    ForeignKey, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class AdaptiveSessionStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"


class AdaptiveStopReason(str, enum.Enum):
    SE_THRESHOLD = "se_threshold"
    MAX_ITEMS = "max_items"
    TIMEOUT = "timeout"
    USER_QUIT = "user_quit"


class AdaptiveQuizSession(BaseModel):
    __tablename__ = "adaptive_quiz_sessions"

    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_area = Column(String(20), nullable=False)

    theta_initial = Column(Numeric(7, 4), default=0.0, nullable=False)
    theta_current = Column(Numeric(7, 4), nullable=False)
    theta_final = Column(Numeric(7, 4), nullable=True)

    se_current = Column(Numeric(6, 4), nullable=False)
    se_final = Column(Numeric(6, 4), nullable=True)

    items_administered = Column(Integer, default=0, nullable=False)
    max_items = Column(Integer, default=20, nullable=False)
    stop_reason = Column(String(30), nullable=True)

    estimated_band = Column(Numeric(3, 1), nullable=True)
    theta_history = Column(JSONB, default=list, nullable=False)

    status = Column(String(20), default=AdaptiveSessionStatus.IN_PROGRESS.value, nullable=False)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    responses = relationship(
        "AdaptiveQuizResponse",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AdaptiveQuizResponse.item_position"
    )

    __table_args__ = (
        Index("idx_adaptive_session_user_skill", "user_id", "skill_area", "status"),
    )


class AdaptiveQuizResponse(BaseModel):
    __tablename__ = "adaptive_quiz_responses"

    session_id = Column(PG_UUID(as_uuid=True), ForeignKey("adaptive_quiz_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(PG_UUID(as_uuid=True), ForeignKey("question_bank.id", ondelete="RESTRICT"), nullable=False, index=True)

    item_position = Column(Integer, nullable=False)

    theta_before = Column(Numeric(7, 4), nullable=False)
    theta_after = Column(Numeric(7, 4), nullable=False)

    se_before = Column(Numeric(6, 4), nullable=False)
    se_after = Column(Numeric(6, 4), nullable=False)

    fisher_info_at_selection = Column(Numeric(10, 6), nullable=True)

    irt_a_used = Column(Numeric(6, 4), nullable=False)
    irt_b_used = Column(Numeric(6, 4), nullable=False)
    irt_c_used = Column(Numeric(6, 4), nullable=False)

    response_data = Column(JSONB, nullable=False)
    is_correct = Column(Boolean, nullable=False)
    time_spent_seconds = Column(Integer, nullable=True)

    # Relationships
    session = relationship("AdaptiveQuizSession", back_populates="responses")
    question = relationship("QuestionBank")

    __table_args__ = (
        UniqueConstraint("session_id", "item_position", name="uq_adaptive_response_session_item"),
    )
