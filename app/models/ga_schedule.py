"""
GA Schedule Models
==================
Tables for Genetic Algorithm schedule optimization:
- GARun: Tracks each GA execution run
- GAScheduleProposal: Individual session proposals from best GA result
- TeacherUnavailability: Teacher availability constraints (input for GA)
"""
from sqlalchemy import (
    Column, String, Integer, SmallInteger, Float, Text, Boolean,
    Date, Time, Enum, ForeignKey, TIMESTAMP, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import BaseModel
import enum


# --- ENUMERATIONS ---

class GARunStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    APPLIED = "applied"


# --- MODELS ---

class GARun(BaseModel):
    """
    Tracks each Genetic Algorithm execution run.
    Stores config, results summary, and status.
    """
    __tablename__ = "ga_runs"

    status = Column(
        Enum(GARunStatus,
             values_callable=lambda obj: [e.value for e in obj],
             native_enum=True,
             name='ga_run_status'),
        default=GARunStatus.PENDING,
        nullable=False
    )

    # Schedule date range
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    # Classes to schedule (null = all active classes)
    class_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)

    # GA Hyperparameters
    config = Column(JSONB, nullable=False, default=dict)
    # Expected structure:
    # {
    #   "population_size": 100,
    #   "generations": 300,
    #   "crossover_rate": 0.70,
    #   "mutation_rate": 0.15,
    #   "elitism_count": 5,
    #   "tournament_size": 5,
    #   "weights": {
    #       "consecutive_limit": 10.0,
    #       "paired_classes": 8.0,
    #       "exam_avoidance": 7.0,
    #       "time_preference": 5.0,
    #       "room_utilization": 3.0,
    #       "preserve_existing": 6.0
    #   }
    # }

    # Result metrics
    best_fitness = Column(Float, nullable=True)
    hard_violations = Column(Integer, nullable=True)
    soft_score = Column(Float, nullable=True)
    generations_run = Column(Integer, nullable=True)

    # Result summary (detailed stats, conflict breakdown, etc.)
    result_summary = Column(JSONB, nullable=True)
    # Expected structure:
    # {
    #   "total_sessions": 50,
    #   "conflict_count": 0,
    #   "statistics": {
    #       "success_rate": 100.0,
    #       "avg_room_utilization": 0.75,
    #       "teachers_scheduled": 8,
    #       "rooms_used": 6
    #   },
    #   "soft_constraint_breakdown": {
    #       "consecutive_limit_satisfied": 45,
    #       "paired_classes_satisfied": 3,
    #       ...
    #   }
    # }

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Timing
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint('start_date <= end_date', name='ga_runs_date_range_check'),
    )

    # Relationships
    proposals = relationship(
        "GAScheduleProposal",
        back_populates="ga_run",
        cascade="all, delete-orphan"
    )


class GAScheduleProposal(BaseModel):
    """
    Individual session proposal from the best GA result.
    Each row represents one proposed class session.
    """
    __tablename__ = "ga_schedule_proposals"

    # Link to GA run
    ga_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey('ga_runs.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Session details
    class_id = Column(
        UUID(as_uuid=True),
        ForeignKey('classes.id', ondelete='CASCADE'),
        nullable=False
    )
    teacher_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=False
    )
    room_id = Column(
        UUID(as_uuid=True),
        ForeignKey('rooms.id', ondelete='SET NULL'),
        nullable=True
    )

    # Time
    session_date = Column(Date, nullable=False)
    time_slots = Column(ARRAY(SmallInteger), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # Content
    lesson_topic = Column(String(255), nullable=True)

    # Conflict tracking
    is_conflict = Column(Boolean, default=False, nullable=False)
    conflict_details = Column(JSONB, nullable=True)
    # Expected structure when is_conflict=True:
    # {
    #   "type": "teacher_clash",
    #   "conflicting_with": "session_uuid",
    #   "reason": "Teacher X already assigned to Class Y at this time"
    # }

    # Relationships
    ga_run = relationship("GARun", back_populates="proposals")
    proposed_class = relationship("Class", foreign_keys=[class_id])
    teacher = relationship("User", foreign_keys=[teacher_id])
    room = relationship("Room", foreign_keys=[room_id])


class TeacherUnavailability(BaseModel):
    """
    Teacher availability constraints.
    Stores dates/times when a teacher is unavailable.
    Supports both one-time and recurring (weekly) unavailability.
    """
    __tablename__ = "teacher_unavailability"

    teacher_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # For one-time unavailability
    unavailable_date = Column(Date, nullable=True)

    # Specific time slots (null = entire day)
    time_slots = Column(ARRAY(SmallInteger), nullable=True)

    # Reason
    reason = Column(String(255), nullable=True)

    # Recurring support
    is_recurring = Column(Boolean, default=False, nullable=False)
    # day_of_week: 0=Monday, 1=Tuesday, ..., 6=Sunday
    day_of_week = Column(SmallInteger, nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            '(is_recurring = false AND unavailable_date IS NOT NULL) OR '
            '(is_recurring = true AND day_of_week IS NOT NULL)',
            name='teacher_unavailability_date_or_recurring_check'
        ),
        CheckConstraint(
            'day_of_week IS NULL OR (day_of_week >= 0 AND day_of_week <= 6)',
            name='teacher_unavailability_day_of_week_check'
        ),
    )

    # Relationships
    teacher = relationship("User", foreign_keys=[teacher_id])
