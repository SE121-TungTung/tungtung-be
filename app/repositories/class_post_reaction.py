"""
Repository: ClassPostReactionRepository
Truy vấn dữ liệu reaction — không chứa business logic.
"""

from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.class_post_reaction import ClassPostReaction
from app.repositories.base import BaseRepository


class ClassPostReactionRepository(BaseRepository[ClassPostReaction]):
    """Repository cho class_post_reactions."""

    def get_user_reaction(
        self,
        db: Session,
        post_id: UUID,
        user_id: UUID,
        reaction_type: str,
    ) -> Optional[ClassPostReaction]:
        """Tìm reaction cụ thể của 1 user trên 1 bài theo type."""
        return (
            db.query(self.model)
            .filter(
                self.model.post_id == post_id,
                self.model.user_id == user_id,
                self.model.reaction_type == reaction_type,
            )
            .first()
        )

    def get_reactions_summary(self, db: Session, post_id: UUID) -> Dict[str, int]:
        """Trả về số lượng reaction mỗi type dưới dạng dict.

        Returns:
            {"like": N, "heart": N, "understood": N}
        """
        rows = (
            db.query(self.model.reaction_type, func.count(self.model.id))
            .filter(self.model.post_id == post_id)
            .group_by(self.model.reaction_type)
            .all()
        )
        summary = {"like": 0, "heart": 0, "understood": 0}
        for reaction_type, count in rows:
            if reaction_type in summary:
                summary[reaction_type] = count
        return summary

    def get_user_reactions_for_post(
        self,
        db: Session,
        post_id: UUID,
        user_id: UUID,
    ) -> List[str]:
        """Trả về danh sách reaction_type mà user đang active trên bài viết này."""
        rows = (
            db.query(self.model.reaction_type)
            .filter(
                self.model.post_id == post_id,
                self.model.user_id == user_id,
            )
            .all()
        )
        return [r[0] for r in rows]

    # ─── Batch methods (tránh N+1) ───────────────────────────────────────────

    def get_reactions_summary_batch(
        self, db: Session, post_ids: List[UUID]
    ) -> Dict[UUID, Dict[str, int]]:
        """1 query duy nhất lấy reaction counts cho TẤT CẢ posts.

        Returns:
            {post_id: {"like": N, "heart": N, "understood": N}, ...}
        """
        if not post_ids:
            return {}

        rows = (
            db.query(
                self.model.post_id,
                self.model.reaction_type,
                func.count(self.model.id),
            )
            .filter(self.model.post_id.in_(post_ids))
            .group_by(self.model.post_id, self.model.reaction_type)
            .all()
        )

        result: Dict[UUID, Dict[str, int]] = {
            pid: {"like": 0, "heart": 0, "understood": 0} for pid in post_ids
        }
        for post_id, reaction_type, count in rows:
            if post_id in result and reaction_type in result[post_id]:
                result[post_id][reaction_type] = count
        return result

    def get_user_reactions_batch(
        self, db: Session, post_ids: List[UUID], user_id: UUID
    ) -> Dict[UUID, List[str]]:
        """1 query duy nhất lấy user reactions cho TẤT CẢ posts.

        Returns:
            {post_id: ["like", "heart"], ...}
        """
        if not post_ids:
            return {}

        rows = (
            db.query(self.model.post_id, self.model.reaction_type)
            .filter(
                self.model.post_id.in_(post_ids),
                self.model.user_id == user_id,
            )
            .all()
        )

        result: Dict[UUID, List[str]] = {pid: [] for pid in post_ids}
        for post_id, reaction_type in rows:
            if post_id in result:
                result[post_id].append(reaction_type)
        return result

    def delete_reaction(self, db: Session, reaction: ClassPostReaction) -> None:
        """Xóa vật lý 1 reaction (unlike/un-heart/un-understood)."""
        db.delete(reaction)
        db.commit()


class_post_reaction_repo = ClassPostReactionRepository(ClassPostReaction)
