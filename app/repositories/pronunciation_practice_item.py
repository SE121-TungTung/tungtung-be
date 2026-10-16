from typing import List, Set
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.pronunciation_practice_item import PronunciationPracticeItem
from app.repositories.base import BaseRepository


class PronunciationPracticeItemRepository(BaseRepository[PronunciationPracticeItem]):
    def __init__(self):
        super().__init__(PronunciationPracticeItem)

    def list_by_context(
        self, db: Session, kind: str, context_key: str
    ) -> List[PronunciationPracticeItem]:
        return (
            db.query(self.model)
            .filter(
                self.model.kind == kind,
                self.model.context_key == context_key,
                self.model.deleted_at.is_(None),
            )
            .all()
        )

    def existing_keys(self, db: Session, kind: str, context_key: str) -> Set[str]:
        rows = (
            db.query(self.model.text_key)
            .filter(
                self.model.kind == kind,
                self.model.context_key == context_key,
                self.model.deleted_at.is_(None),
            )
            .all()
        )
        return {r[0] for r in rows}

    def create_many(
        self, db: Session, items: List[dict]
    ) -> List[PronunciationPracticeItem]:
        """Thêm từng item, bỏ qua item trùng (race condition giữa các request)."""
        created: List[PronunciationPracticeItem] = []
        for data in items:
            obj = self.model(**data)
            db.add(obj)
            try:
                db.commit()
                db.refresh(obj)
                created.append(obj)
            except IntegrityError:
                db.rollback()
        return created

    def increment_usage(self, db: Session, ids: List[UUID]) -> None:
        if not ids:
            return
        db.query(self.model).filter(self.model.id.in_(ids)).update(
            {self.model.usage_count: self.model.usage_count + 1},
            synchronize_session=False,
        )
        db.commit()


pronunciation_practice_item_repo = PronunciationPracticeItemRepository()
