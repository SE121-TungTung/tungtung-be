"""
Schema: Class Post Reactions (Toggle Like/Heart/Understood)
Định nghĩa Request và Response schemas cho reaction trên bài viết lớp học.
"""

from typing import List, Literal
from pydantic import BaseModel, Field


# ─── Request Schemas ──────────────────────────────────────────────────────────

class ReactionToggleRequest(BaseModel):
    """Body để toggle một reaction."""
    reaction_type: Literal["like", "heart", "understood"] = Field(
        ...,
        description="Loại reaction: 'like' (Thích) | 'heart' (Yêu thích) | 'understood' (Đã hiểu)"
    )


# ─── Response Schemas ─────────────────────────────────────────────────────────

class ReactionsSummary(BaseModel):
    """Tóm tắt số lượng reaction trên 1 bài viết và reaction hiện tại của user."""
    like:          int         = 0
    heart:         int         = 0
    understood:    int         = 0
    # Các reaction mà current_user đang active trên bài này
    user_reactions: List[str] = []


class ReactionToggleResponse(BaseModel):
    """Response sau khi toggle reaction."""
    action:        Literal["added", "removed"]
    reaction_type: str
    summary:       ReactionsSummary
