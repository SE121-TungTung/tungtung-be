# app/repositories/notification.py
from sqlalchemy.orm import Session
from app.models.notification import Notification
from app.repositories.base import BaseRepository
from uuid import UUID
from typing import List
from sqlalchemy import func


class NotificationRepository(BaseRepository[Notification]):
    def get_by_user(
        self,
        db: Session,
        user_id: UUID,
        skip: int = 0,
        limit: int = 100,
        unread_only: bool = False,
    ) -> List[Notification]:
        query = db.query(self.model).filter(self.model.user_id == user_id)
        if unread_only:
            query = query.filter(self.model.read_at.is_(None))
        return (
            query.order_by(self.model.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_user(
        self, db: Session, user_id: UUID, unread_only: bool = False
    ) -> int:
        query = db.query(func.count(self.model.id)).filter(
            self.model.user_id == user_id
        )
        if unread_only:
            query = query.filter(self.model.read_at.is_(None))
        return query.scalar() or 0

    def count_unread(self, db: Session, user_id: UUID) -> int:
        return (
            db.query(func.count(self.model.id))
            .filter(
                self.model.user_id == user_id, self.model.read_at.is_(None)
            )
            .scalar()
            or 0
        )

    def mark_all_as_read(self, db: Session, user_id: UUID) -> int:
        result = db.query(self.model).filter(
            self.model.user_id == user_id,
            self.model.read_at.is_(None),  # Chỉ update những cái chưa đọc (read_at is Null)
        ).update(
            {self.model.read_at: func.now()},
            synchronize_session=False,  # Tối ưu hiệu năng cho bulk update
        )
        return result


notification_repo = NotificationRepository(Notification)
