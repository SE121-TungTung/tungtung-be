"""
Schemas: Flashcard
Covers: FlashcardDeck, Flashcard, FlashcardReview, Stats
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime, date
from pydantic import BaseModel, Field, field_validator

from app.models.flashcard import TopicTag, DeckLevel, WordType, ReviewState, Rating


# ---------------------------------------------------------------------------
# FlashcardDeck Schemas
# ---------------------------------------------------------------------------

class FlashcardDeckCreate(BaseModel):
    """POST /flashcard-decks"""
    title: str = Field(..., min_length=1, max_length=255, description="Tên deck thẻ")
    description: Optional[str] = Field(None, description="Mô tả deck")
    topic_tag: Optional[TopicTag] = Field(None, description="Chủ đề: ielts, toeic, general...")
    level: Optional[DeckLevel] = Field(None, description="Trình độ: beginner, intermediate, advanced, expert")
    is_public: bool = Field(False, description="Deck công khai hay riêng tư")
    cover_image_url: Optional[str] = Field(None, max_length=500, description="URL ảnh bìa")


class FlashcardDeckUpdate(BaseModel):
    """PUT /flashcard-decks/{id}"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    topic_tag: Optional[TopicTag] = None
    level: Optional[DeckLevel] = None
    is_public: Optional[bool] = None
    cover_image_url: Optional[str] = Field(None, max_length=500)


class FlashcardDeckResponse(BaseModel):
    """Deck response trả về client"""
    id: UUID
    title: str
    description: Optional[str] = None
    topic_tag: Optional[str] = None
    level: Optional[str] = None
    is_public: bool
    card_count: int
    cover_image_url: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Computed field: số thẻ đến hạn hôm nay (được inject từ service)
    due_today_count: int = Field(0, description="Số thẻ cần ôn hôm nay trong deck này")

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Flashcard (Card) Schemas
# ---------------------------------------------------------------------------

class FlashcardCreate(BaseModel):
    """POST /flashcard-decks/{id}/cards"""
    word: str = Field(..., min_length=1, max_length=200, description="Từ vựng")
    ipa: Optional[str] = Field(None, max_length=200, description="Phiên âm IPA")
    word_type: Optional[WordType] = Field(None, description="Loại từ")
    definition_en: Optional[str] = Field(None, description="Định nghĩa tiếng Anh")
    definition_vi: Optional[str] = Field(None, description="Định nghĩa tiếng Việt")
    example_sentence: Optional[str] = Field(None, description="Câu ví dụ")
    audio_url: Optional[str] = Field(None, max_length=500, description="URL audio phát âm")
    source_vocabulary_id: Optional[UUID] = Field(None, description="ID từ vựng gốc trong user_vocabulary")


class FlashcardUpdate(BaseModel):
    """PUT /flashcard-decks/{id}/cards/{card_id}"""
    word: Optional[str] = Field(None, min_length=1, max_length=200)
    ipa: Optional[str] = Field(None, max_length=200)
    word_type: Optional[WordType] = None
    definition_en: Optional[str] = None
    definition_vi: Optional[str] = None
    example_sentence: Optional[str] = None
    audio_url: Optional[str] = Field(None, max_length=500)


class FlashcardResponse(BaseModel):
    """Card response trả về client"""
    id: UUID
    deck_id: UUID
    word: str
    ipa: Optional[str] = None
    word_type: Optional[str] = None
    definition_en: Optional[str] = None
    definition_vi: Optional[str] = None
    example_sentence: Optional[str] = None
    audio_url: Optional[str] = None
    source_vocabulary_id: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FlashcardWithReviewResponse(FlashcardResponse):
    """Card kèm FSRS state hiện tại của user (dùng cho /due endpoint)"""
    review_state: Optional[str] = Field(None, description="new | learning | review | relearning")
    due_date: Optional[datetime] = None
    stability: Optional[float] = None
    difficulty: Optional[float] = None


# ---------------------------------------------------------------------------
# Review (FSRS) Schemas
# ---------------------------------------------------------------------------

class ReviewSubmitRequest(BaseModel):
    """POST /flashcards/reviews"""
    card_id: UUID = Field(..., description="UUID của thẻ cần review")
    rating: int = Field(
        ..., ge=1, le=4,
        description="1=Again, 2=Hard, 3=Good, 4=Easy"
    )

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v):
        if v not in (1, 2, 3, 4):
            raise ValueError("Rating must be 1 (Again), 2 (Hard), 3 (Good), or 4 (Easy)")
        return v

    def to_rating_enum(self) -> Rating:
        mapping = {1: Rating.AGAIN, 2: Rating.HARD, 3: Rating.GOOD, 4: Rating.EASY}
        return mapping[self.rating]


class ReviewResponse(BaseModel):
    """Response sau khi submit review"""
    card_id: UUID
    state: str = Field(..., description="Trạng thái FSRS mới: new | learning | review | relearning")
    stability: float = Field(..., description="Độ bền vững trí nhớ (ngày)")
    difficulty: float = Field(..., description="Mức độ khó (1-10)")
    retrievability: Optional[float] = Field(None, description="Xác suất nhớ đúng hiện tại")
    repetition_count: int
    lapses: int
    interval_days: int = Field(..., description="Số ngày đến lần ôn tiếp theo")
    due_date: datetime = Field(..., description="Thời điểm ôn lại kế tiếp")
    last_rating: str = Field(..., description="Rating vừa submit: again | hard | good | easy")

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Stats Schemas
# ---------------------------------------------------------------------------

class DailyActivity(BaseModel):
    date: date
    count: int = Field(..., description="Số thẻ đã ôn trong ngày")


class FlashcardStatsResponse(BaseModel):
    """GET /flashcards/stats"""
    total_reviews: int = Field(..., description="Tổng số lần review")
    total_mastered: int = Field(..., description="Tổng thẻ đã thuộc (state=review, reps >= 3)")
    streak_days: int = Field(..., description="Số ngày liên tiếp ôn bài")
    due_today: int = Field(..., description="Số thẻ cần ôn hôm nay")
    heatmap: List[DailyActivity] = Field(
        default_factory=list,
        description="Hoạt động 30 ngày gần nhất"
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Import from vocabulary
# ---------------------------------------------------------------------------

class ImportFromVocabularyRequest(BaseModel):
    """POST /flashcards/import-from-vocabulary"""
    deck_id: UUID = Field(..., description="UUID của deck đích")
    vocabulary_ids: List[UUID] = Field(
        ..., min_length=1, max_length=100,
        description="Danh sách ID từ user_vocabulary cần import (tối đa 100 từ)"
    )
