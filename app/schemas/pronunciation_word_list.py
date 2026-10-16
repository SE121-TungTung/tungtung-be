"""
Schemas: Pronunciation Word List (liên kết Flashcard <-> Pronunciation)
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class WordListAddRequest(BaseModel):
    """POST /pronunciation/word-list — cần `target_text` hoặc `flashcard_id`."""
    target_text: Optional[str] = Field(None, min_length=1, max_length=500)
    target_type: Optional[str] = Field(None, pattern="^(word|phrase|sentence)$")
    ipa: Optional[str] = Field(None, max_length=200)
    flashcard_id: Optional[UUID] = Field(None, description="Thẻ flashcard nguồn")


class WordListItemResponse(BaseModel):
    id: UUID
    target_text: str
    target_type: str
    ipa: Optional[str] = None
    ipa_us: Optional[str] = None
    ipa_uk: Optional[str] = None
    source: str
    flashcard_id: Optional[UUID] = None
    deck_id: Optional[UUID] = None
    created_at: datetime
    practice_count: int = 0
    best_score: Optional[float] = None
    last_score: Optional[float] = None
    last_practiced_at: Optional[datetime] = None


class WordListResponse(BaseModel):
    items: List[WordListItemResponse]
    total: int
