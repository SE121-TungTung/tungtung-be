from sqlalchemy import Column, String, Numeric, Integer, Boolean, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

from app.models.base import BaseModel

class RecommendationLog(BaseModel):
    __tablename__ = "recommendation_logs"

    student_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    skill_scores   = Column(JSONB)         # {"reading": 5.5, ...}
    attendance_rate= Column(Numeric(5,2))
    target_band    = Column(Numeric(3,1))
    target_cefr    = Column(String(5))      # "B2", "C1"

    predicted_band = Column(Numeric(3,1))
    predicted_cefr = Column(String(5))
    weakest_skill  = Column(String(50))
    estimated_weeks= Column(Integer)

    recommendation_type = Column(String(50))  # daily_practice|mock_exam|nudge
    recommendation_data = Column(JSONB)       # {title, tips, materials}
    learning_path       = Column(JSONB)       # {milestones}

    is_read       = Column(Boolean, default=False)
    generated_at  = Column(TIMESTAMP(timezone=True), default=func.now())
