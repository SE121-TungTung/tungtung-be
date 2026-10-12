"""Repository layer for Adaptive Quiz (CAT & IRT).

Provides database query interfaces for:
- AdaptiveQuizSession
- AdaptiveQuizResponse
- QuestionBank (IRT parameters & CAT question pool)
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.adaptive_quiz import (
    AdaptiveQuizResponse,
    AdaptiveQuizSession,
    AdaptiveSessionStatus,
)
from app.models.test import (
    ContentStatus,
    DifficultyLevel,
    QuestionBank,
    QuestionType,
    SkillArea,
)
from app.repositories.base import BaseRepository


class AdaptiveQuizSessionRepository(BaseRepository[AdaptiveQuizSession]):
    def __init__(self):
        super().__init__(AdaptiveQuizSession)

    def get_by_id(self, db: Session, session_id: UUID) -> Optional[AdaptiveQuizSession]:
        return (
            db.query(AdaptiveQuizSession)
            .options(joinedload(AdaptiveQuizSession.responses).joinedload(AdaptiveQuizResponse.question))
            .filter(
                AdaptiveQuizSession.id == session_id,
                AdaptiveQuizSession.deleted_at.is_(None),
            )
            .first()
        )

    def get_active_session(
        self, db: Session, user_id: UUID, skill_area: str
    ) -> Optional[AdaptiveQuizSession]:
        return (
            db.query(AdaptiveQuizSession)
            .filter(
                AdaptiveQuizSession.user_id == user_id,
                AdaptiveQuizSession.skill_area == skill_area,
                AdaptiveQuizSession.status == AdaptiveSessionStatus.IN_PROGRESS.value,
                AdaptiveQuizSession.deleted_at.is_(None),
            )
            .first()
        )

    def list_by_user(
        self,
        db: Session,
        user_id: UUID,
        skill_area: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[AdaptiveQuizSession], int]:
        query = db.query(AdaptiveQuizSession).filter(
            AdaptiveQuizSession.user_id == user_id,
            AdaptiveQuizSession.deleted_at.is_(None),
        )

        if skill_area:
            query = query.filter(AdaptiveQuizSession.skill_area == skill_area)

        total = query.count()
        offset = (page - 1) * page_size
        items = (
            query.order_by(AdaptiveQuizSession.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return items, total

    def count_today_sessions(self, db: Session, user_id: UUID) -> int:
        now = datetime.now(timezone.utc)
        start_of_day = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        return (
            db.query(func.count(AdaptiveQuizSession.id))
            .filter(
                AdaptiveQuizSession.user_id == user_id,
                AdaptiveQuizSession.created_at >= start_of_day,
                AdaptiveQuizSession.deleted_at.is_(None),
            )
            .scalar()
            or 0
        )

    def count_recent_placement_tests(self, db: Session, user_id: UUID, days: int = 30) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return (
            db.query(func.count(AdaptiveQuizSession.id))
            .filter(
                AdaptiveQuizSession.user_id == user_id,
                AdaptiveQuizSession.status == AdaptiveSessionStatus.COMPLETED.value,
                AdaptiveQuizSession.created_at >= cutoff,
                AdaptiveQuizSession.deleted_at.is_(None),
            )
            .scalar()
            or 0
        )


class AdaptiveQuizResponseRepository(BaseRepository[AdaptiveQuizResponse]):
    def __init__(self):
        super().__init__(AdaptiveQuizResponse)

    def list_by_session(
        self, db: Session, session_id: UUID
    ) -> List[AdaptiveQuizResponse]:
        return (
            db.query(AdaptiveQuizResponse)
            .options(joinedload(AdaptiveQuizResponse.question))
            .filter(
                AdaptiveQuizResponse.session_id == session_id,
                AdaptiveQuizResponse.deleted_at.is_(None),
            )
            .order_by(AdaptiveQuizResponse.item_position.asc())
            .all()
        )


class AdaptiveQuestionPoolRepository(BaseRepository[QuestionBank]):
    def __init__(self):
        super().__init__(QuestionBank)

    def get_cat_pool(
        self, db: Session, skill_area: str, exclude_ids: Optional[List[UUID]] = None
    ) -> List[QuestionBank]:
        # Filter for active, non-deleted, auto-gradable, cat-eligible items
        query = db.query(QuestionBank).filter(
            QuestionBank.deleted_at.is_(None),
            QuestionBank.status == ContentStatus.ACTIVE,
            QuestionBank.skill_area == skill_area,
            QuestionBank.is_cat_eligible == True,
            QuestionBank.irt_calibrated == True,
        )

        if exclude_ids:
            query = query.filter(QuestionBank.id.notin_(exclude_ids))

        return query.all()

    def list_questions(
        self,
        db: Session,
        skill_area: Optional[str] = None,
        calibrated: Optional[bool] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[QuestionBank], int]:
        query = db.query(QuestionBank).filter(
            QuestionBank.deleted_at.is_(None),
            QuestionBank.status == ContentStatus.ACTIVE,
        )

        if skill_area:
            query = query.filter(QuestionBank.skill_area == skill_area)

        if calibrated is not None:
            query = query.filter(QuestionBank.irt_calibrated == calibrated)

        if search:
            query = query.filter(
                or_(
                    QuestionBank.title.ilike(f"%{search}%"),
                    QuestionBank.question_text.ilike(f"%{search}%"),
                )
            )

        total = query.count()
        offset = (page - 1) * page_size
        items = (
            query.order_by(QuestionBank.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )
        return items, total

    def update_irt(
        self,
        db: Session,
        question_id: UUID,
        a: float,
        b: float,
        c: float,
        calibrated: bool = True,
        is_cat_eligible: bool = True,
    ) -> Optional[QuestionBank]:
        question = (
            db.query(QuestionBank)
            .filter(QuestionBank.id == question_id, QuestionBank.deleted_at.is_(None))
            .first()
        )
        if not question:
            return None

        question.irt_discrimination = a
        question.irt_difficulty = b
        question.irt_guessing = c
        question.irt_calibrated = calibrated
        question.irt_calibrated_at = datetime.now(timezone.utc)
        question.is_cat_eligible = is_cat_eligible

        db.commit()
        db.refresh(question)
        return question

    def get_stats(self, db: Session) -> Dict[str, Any]:
        base_query = db.query(QuestionBank).filter(
            QuestionBank.deleted_at.is_(None),
            QuestionBank.status == ContentStatus.ACTIVE,
        )

        total_questions = base_query.count()
        calibrated_count = base_query.filter(QuestionBank.irt_calibrated == True).count()
        cat_eligible_count = base_query.filter(QuestionBank.is_cat_eligible == True).count()

        reading_total = base_query.filter(QuestionBank.skill_area == SkillArea.READING).count()
        reading_calibrated = base_query.filter(
            QuestionBank.skill_area == SkillArea.READING, QuestionBank.irt_calibrated == True
        ).count()

        listening_total = base_query.filter(QuestionBank.skill_area == SkillArea.LISTENING).count()
        listening_calibrated = base_query.filter(
            QuestionBank.skill_area == SkillArea.LISTENING, QuestionBank.irt_calibrated == True
        ).count()

        avg_diff = (
            db.query(func.avg(QuestionBank.irt_difficulty))
            .filter(
                QuestionBank.deleted_at.is_(None),
                QuestionBank.irt_calibrated == True,
            )
            .scalar()
            or 0.0
        )

        avg_disc = (
            db.query(func.avg(QuestionBank.irt_discrimination))
            .filter(
                QuestionBank.deleted_at.is_(None),
                QuestionBank.irt_calibrated == True,
            )
            .scalar()
            or 1.0
        )

        return {
            "total_questions": total_questions,
            "calibrated_count": calibrated_count,
            "cat_eligible_count": cat_eligible_count,
            "calibration_rate": round((calibrated_count / total_questions) * 100, 1)
            if total_questions > 0
            else 0.0,
            "reading": {
                "total": reading_total,
                "calibrated": reading_calibrated,
            },
            "listening": {
                "total": listening_total,
                "calibrated": listening_calibrated,
            },
            "avg_difficulty": round(float(avg_diff), 4),
            "avg_discrimination": round(float(avg_disc), 4),
        }
