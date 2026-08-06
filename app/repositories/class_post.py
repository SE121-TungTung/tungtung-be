from sqlalchemy.orm import Session
from app.models.class_post import ClassPost
from app.repositories.base import BaseRepository
from uuid import UUID
from typing import List
from sqlalchemy import func

class ClassPostRepository(BaseRepository[ClassPost]):
    def get_by_class(self, db: Session, class_id: UUID, skip: int = 0, limit: int = 20) -> List[ClassPost]:
        return db.query(self.model)\
            .filter(self.model.class_id == class_id)\
            .order_by(self.model.created_at.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()

    def count_by_class(self, db: Session, class_id: UUID) -> int:
        return db.query(func.count(self.model.id))\
            .filter(self.model.class_id == class_id)\
            .scalar()

class_post_repo = ClassPostRepository(ClassPost)
