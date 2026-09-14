"""
Service Layer: ClassPostReactionService
Xử lý business logic toggle reaction (Like / Heart / Understood) trên bài viết lớp học.

Toggle semantics:
  - Nếu đã có reaction cùng type → DELETE (action = "removed")
  - Nếu chưa có → INSERT (action = "added")
  - 1 user có thể có nhiều type reaction cùng lúc trên 1 bài viết.
"""

from typing import Dict
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.class_post import ClassPost
from app.models.class_post_reaction import ClassPostReaction
from app.repositories.class_post_reaction import class_post_reaction_repo
from app.schemas.class_post_reaction import ReactionsSummary, ReactionToggleResponse


VALID_REACTION_TYPES = {"like", "heart", "understood"}


def toggle_reaction(
    db: Session,
    post: ClassPost,
    user_id: UUID,
    reaction_type: str,
) -> ReactionToggleResponse:
    """Toggle reaction trên 1 bài viết.

    Args:
        reaction_type: "like" | "heart" | "understood"

    Returns:
        ReactionToggleResponse với action ("added"/"removed") và summary mới.
    """
    if reaction_type not in VALID_REACTION_TYPES:
        from app.core.exceptions import APIException
        raise APIException(
            status_code=400,
            code="REACTION_INVALID_TYPE",
            message=f"Loại reaction không hợp lệ: '{reaction_type}'. Chỉ chấp nhận: like, heart, understood.",
        )

    existing = class_post_reaction_repo.get_user_reaction(
        db, post_id=post.id, user_id=user_id, reaction_type=reaction_type
    )

    if existing:
        # Đã react → bỏ react (hard delete)
        class_post_reaction_repo.delete_reaction(db, reaction=existing)
        action = "removed"
    else:
        # Chưa react → thêm react
        new_reaction = ClassPostReaction(
            post_id=post.id,
            user_id=user_id,
            reaction_type=reaction_type,
        )
        db.add(new_reaction)
        db.commit()
        action = "added"

    # Tính toán summary sau khi toggle
    counts: Dict[str, int] = class_post_reaction_repo.get_reactions_summary(db, post_id=post.id)
    user_reactions = class_post_reaction_repo.get_user_reactions_for_post(db, post_id=post.id, user_id=user_id)

    summary = ReactionsSummary(
        like=counts.get("like", 0),
        heart=counts.get("heart", 0),
        understood=counts.get("understood", 0),
        user_reactions=user_reactions,
    )

    return ReactionToggleResponse(
        action=action,
        reaction_type=reaction_type,
        summary=summary,
    )
