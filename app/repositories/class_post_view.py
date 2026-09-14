"""
Repository: ClassPostViewRepository
Truy vấn dữ liệu lượt xem (view tracking) — không chứa business logic.
"""

from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.class_post_view import ClassPostView
from app.models.academic import ClassEnrollment
from app.models.user import User
from app.schemas.class_post_view import ViewerInfo, ViewersSummaryResponse
from app.repositories.base import BaseRepository


class ClassPostViewRepository(BaseRepository[ClassPostView]):
    """Repository cho class_post_views."""

    def record_view(
        self,
        db: Session,
        post_id: UUID,
        user_id: UUID,
    ) -> Tuple[ClassPostView, bool]:
        """Ghi nhận lượt xem của user trên bài viết.

        Returns:
            (view_record, is_new): is_new = True nếu vừa ghi nhận lần đầu.
        """
        existing = (
            db.query(self.model)
            .filter(
                self.model.post_id == post_id,
                self.model.user_id == user_id,
            )
            .first()
        )
        if existing:
            return existing, False

        new_view = self.model(post_id=post_id, user_id=user_id)
        db.add(new_view)
        db.commit()
        db.refresh(new_view)
        return new_view, True

    def get_view_count(self, db: Session, post_id: UUID) -> int:
        """Đếm tổng số lượt xem duy nhất trên 1 bài viết."""
        return (
            db.query(func.count(self.model.id))
            .filter(self.model.post_id == post_id)
            .scalar()
            or 0
        )

    def get_view_counts_batch(self, db: Session, post_ids: List[UUID]) -> dict:
        """Đếm số lượt xem cho nhiều bài viết cùng lúc."""
        if not post_ids:
            return {}
        rows = (
            db.query(self.model.post_id, func.count(self.model.id))
            .filter(self.model.post_id.in_(post_ids))
            .group_by(self.model.post_id)
            .all()
        )
        return {post_id: count for post_id, count in rows}

    def get_viewers_summary(
        self,
        db: Session,
        post_id: UUID,
        class_id: UUID,
    ) -> ViewersSummaryResponse:
        """Lấy danh sách học viên trong lớp và trạng thái đã xem / chưa xem bài viết."""
        # 1. Danh sách học viên hợp lệ ghi danh trong lớp
        enrollment_rows = (
            db.query(ClassEnrollment, User)
            .join(User, ClassEnrollment.student_id == User.id)
            .filter(
                ClassEnrollment.class_id == class_id,
                ClassEnrollment.deleted_at.is_(None),
                User.deleted_at.is_(None),
            )
            .all()
        )

        # 2. Lấy toàn bộ lượt xem của bài viết này
        views = (
            db.query(self.model)
            .filter(self.model.post_id == post_id)
            .all()
        )
        view_map = {v.user_id: v.viewed_at for v in views}

        # 3. Phân chia viewers và non_viewers
        viewers: List[ViewerInfo] = []
        non_viewers: List[ViewerInfo] = []

        seen_users = set()
        for enrollment, user in enrollment_rows:
            if user.id in seen_users:
                continue
            seen_users.add(user.id)

            full_name = f"{user.first_name} {user.last_name}".strip() or user.email
            viewed_at = view_map.get(user.id)

            info = ViewerInfo(
                user_id=user.id,
                name=full_name,
                email=user.email,
                avatar_url=user.avatar_url,
                viewed_at=viewed_at,
            )

            if viewed_at is not None:
                viewers.append(info)
            else:
                non_viewers.append(info)

        # Sắp xếp: đã xem thì người xem gần nhất lên đầu; chưa xem thì theo tên A-Z
        viewers.sort(key=lambda x: x.viewed_at or '', reverse=True)
        non_viewers.sort(key=lambda x: x.name.lower())

        total = len(seen_users)
        return ViewersSummaryResponse(
            post_id=post_id,
            total_students=total,
            viewed_count=len(viewers),
            not_viewed_count=len(non_viewers),
            viewers=viewers,
            non_viewers=non_viewers,
        )


class_post_view_repo = ClassPostViewRepository(ClassPostView)
