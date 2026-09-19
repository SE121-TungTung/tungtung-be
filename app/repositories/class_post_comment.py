"""
Repository: ClassPostCommentRepository
Truy vấn dữ liệu bình luận — không chứa business logic.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.class_post_comment import ClassPostComment
from app.repositories.base import BaseRepository


class ClassPostCommentRepository(BaseRepository[ClassPostComment]):
    """Repository cho class_post_comments."""

    def get_by_post(
        self,
        db: Session,
        post_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ClassPostComment]:
        """Lấy danh sách top-level comments (parent_comment_id IS NULL) của 1 bài viết.

        - Chỉ trả về comments active (deleted_at IS NULL).
        - Eager load author và replies (1 cấp, đã filter deleted).
        - Sắp xếp theo created_at ASC (comment cũ nhất hiển thị trước).
        """
        return (
            db.query(self.model)
            .filter(
                self.model.post_id == post_id,
                self.model.parent_comment_id.is_(None),  # top-level only
                self.model.deleted_at.is_(None),
            )
            .options(
                joinedload(self.model.author),
                joinedload(self.model.replies).joinedload(ClassPostComment.author),
            )
            .order_by(self.model.created_at.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def count_by_post(self, db: Session, post_id: UUID) -> int:
        """Đếm tổng số active comments (kể cả replies) của 1 bài viết."""
        return (
            db.query(func.count(self.model.id))
            .filter(
                self.model.post_id == post_id,
                self.model.deleted_at.is_(None),
            )
            .scalar()
            or 0
        )

    def get_active_by_id(
        self,
        db: Session,
        comment_id: UUID,
        post_id: UUID,
    ) -> Optional[ClassPostComment]:
        """Lấy 1 comment active theo ID và post_id (bảo vệ cross-post access)."""
        return (
            db.query(self.model)
            .filter(
                self.model.id == comment_id,
                self.model.post_id == post_id,
                self.model.deleted_at.is_(None),
            )
            .options(joinedload(self.model.author))
            .first()
        )

    def soft_delete(
        self,
        db: Session,
        comment: ClassPostComment,
        deleted_by_id: UUID,
    ) -> None:
        """Xóa mềm bình luận — set deleted_at và updated_by."""
        now = datetime.now(timezone.utc)
        comment.deleted_at = now
        comment.updated_by = deleted_by_id
        db.commit()


class_post_comment_repo = ClassPostCommentRepository(ClassPostComment)
