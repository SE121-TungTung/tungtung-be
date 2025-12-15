# app/repositories/notification.py
from sqlalchemy.orm import Session
from app.models.notification import Notification
from app.repositories.base import BaseRepository
from uuid import UUID
from typing import List

class NotificationRepository(BaseRepository[Notification]):
    def get_by_user(self, db: Session, user_id: UUID, skip: int = 0, limit: int = 100) -> List[Notification]:
        return db.query(self.model)\
            .filter(self.model.user_id == user_id)\
            .order_by(self.model.created_at.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()

    def count_unread(self, db: Session, user_id: UUID) -> int:
        return db.query(self.model)\
            .filter(self.model.user_id == user_id, self.model.read_at == None)\
            .count()

notification_repo = NotificationRepository(Notification)