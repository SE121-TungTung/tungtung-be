from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.class_post import ClassPost, ClassPostType
from app.repositories.base import BaseRepository
from uuid import UUID
from typing import List, Optional


class ClassPostRepository(BaseRepository[ClassPost]):
    """Repository cho class_posts — chỉ truy vấn, không chứa business logic."""

    def get_by_class(
        self,
        db: Session,
        class_id: UUID,
        skip: int = 0,
        limit: int = 20,
        post_type: Optional[ClassPostType] = None,
    ) -> List[ClassPost]:
        """Lấy danh sách bài viết active của lớp.

        - Lọc deleted_at IS NULL (soft-delete).
        - Bài ghim (is_pinned=True) luôn đứng đầu.
        - Trong nhóm ghim sắp xếp theo pinned_at DESC (ghim mới nhất trước).
        - Còn lại sắp xếp theo created_at DESC.
        """
        q = (
            db.query(self.model)
            .filter(
                self.model.class_id == class_id,
                self.model.deleted_at == None,   # noqa: E711 — SQLAlchemy idiom
            )
        )
        if post_type is not None:
            q = q.filter(self.model.post_type == post_type)

        return (
            q.order_by(
                self.model.is_pinned.desc(),
                self.model.pinned_at.desc().nullslast(),
                self.model.created_at.desc(),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_class(
        self,
        db: Session,
        class_id: UUID,
        post_type: Optional[ClassPostType] = None,
    ) -> int:
        """Đếm số bài active trong lớp (deleted_at IS NULL)."""
        q = db.query(func.count(self.model.id)).filter(
            self.model.class_id == class_id,
            self.model.deleted_at == None,   # noqa: E711
        )
        if post_type is not None:
            q = q.filter(self.model.post_type == post_type)
        return q.scalar() or 0

    def get_active_post_by_id(
        self,
        db: Session,
        post_id: UUID,
        class_id: UUID,
    ) -> Optional[ClassPost]:
        """Lấy bài viết theo ID — chỉ trả về nếu chưa bị xóa mềm."""
        return (
            db.query(self.model)
            .filter(
                self.model.id == post_id,
                self.model.class_id == class_id,
                self.model.deleted_at == None,   # noqa: E711
            )
            .first()
        )

    def get_pinned_count(self, db: Session, class_id: UUID) -> int:
        """Đếm số bài đang ghim trong lớp (dùng để enforce giới hạn 3 bài)."""
        return (
            db.query(func.count(self.model.id))
            .filter(
                self.model.class_id == class_id,
                self.model.is_pinned == True,    # noqa: E712
                self.model.deleted_at == None,   # noqa: E711
            )
            .scalar()
            or 0
        )

    def get_oldest_pinned(
        self, db: Session, class_id: UUID
    ) -> Optional[ClassPost]:
        """Lấy bài ghim cũ nhất theo pinned_at ASC.

        Dùng khi FE xác nhận unpin bài cũ nhất để nhường chỗ cho bài mới.
        """
        return (
            db.query(self.model)
            .filter(
                self.model.class_id == class_id,
                self.model.is_pinned == True,    # noqa: E712
                self.model.deleted_at == None,   # noqa: E711
            )
            .order_by(self.model.pinned_at.asc())
            .first()
        )


class_post_repo = ClassPostRepository(ClassPost)
