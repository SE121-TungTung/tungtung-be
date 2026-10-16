from typing import Dict, List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.models.pronunciation import PronunciationPractice
from app.models.pronunciation_word_list import PronunciationWordListItem
from app.repositories.base import BaseRepository


class PronunciationWordListRepository(BaseRepository[PronunciationWordListItem]):
    def __init__(self):
        super().__init__(PronunciationWordListItem)

    def get_by_id(
        self, db: Session, item_id: UUID, student_id: UUID
    ) -> Optional[PronunciationWordListItem]:
        return (
            db.query(self.model)
            .filter(
                self.model.id == item_id,
                self.model.student_id == student_id,
                self.model.deleted_at.is_(None),
            )
            .first()
        )

    def get_by_key(
        self, db: Session, student_id: UUID, text_key: str
    ) -> Optional[PronunciationWordListItem]:
        return (
            db.query(self.model)
            .filter(
                self.model.student_id == student_id,
                self.model.text_key == text_key,
                self.model.deleted_at.is_(None),
            )
            .first()
        )

    def list_by_student(
        self, db: Session, student_id: UUID, limit: int = 200
    ) -> Tuple[List[PronunciationWordListItem], int]:
        query = db.query(self.model).filter(
            self.model.student_id == student_id,
            self.model.deleted_at.is_(None),
        )
        total = query.count()
        items = query.order_by(desc(self.model.created_at)).limit(limit).all()
        return items, total

    def soft_delete(self, db: Session, item: PronunciationWordListItem) -> None:
        item.deleted_at = datetime.now(timezone.utc)
        db.commit()

    def get_practice_stats_by_text(
        self, db: Session, student_id: UUID, text_keys: List[str]
    ) -> Dict[str, dict]:
        """Thống kê luyện tập (số lần, điểm cao nhất, điểm gần nhất) theo text chuẩn hoá."""
        if not text_keys:
            return {}
        key_expr = func.lower(func.trim(PronunciationPractice.target_text))
        rows = (
            db.query(
                key_expr.label("k"),
                func.count(PronunciationPractice.id),
                func.max(PronunciationPractice.overall_score),
                func.max(PronunciationPractice.created_at),
            )
            .filter(
                PronunciationPractice.student_id == student_id,
                PronunciationPractice.deleted_at.is_(None),
                key_expr.in_(text_keys),
            )
            .group_by(key_expr)
            .all()
        )
        stats: Dict[str, dict] = {
            r[0]: {
                "practice_count": r[1],
                "best_score": float(r[2]) if r[2] is not None else None,
                "last_practiced_at": r[3],
                "last_score": None,
            }
            for r in rows
        }
        # Điểm của lượt gần nhất cho từng text
        for key, st in stats.items():
            last = (
                db.query(PronunciationPractice.overall_score)
                .filter(
                    PronunciationPractice.student_id == student_id,
                    PronunciationPractice.deleted_at.is_(None),
                    key_expr == key,
                )
                .order_by(desc(PronunciationPractice.created_at))
                .first()
            )
            if last and last[0] is not None:
                st["last_score"] = float(last[0])
        return stats


pronunciation_word_list_repo = PronunciationWordListRepository()
