import enum
from sqlalchemy import Column, String, Text, Integer, Boolean, Float, ForeignKey, Index, UniqueConstraint, Enum, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class TopicTag(enum.Enum):
    IELTS = "ielts"
    TOEIC = "toeic"
    GENERAL = "general"
    BUSINESS = "business"
    ACADEMIC = "academic"
    OTHER = "other"

class DeckLevel(enum.Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"

class WordType(enum.Enum):
    NOUN = "noun"
    VERB = "verb"
    ADJECTIVE = "adjective"
    ADVERB = "adverb"
    PRONOUN = "pronoun"
    PREPOSITION = "preposition"
    CONJUNCTION = "conjunction"
    INTERJECTION = "interjection"
    PHRASE = "phrase"

class ReviewState(enum.Enum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    RELEARNING = "relearning"

class Rating(enum.Enum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class FlashcardDeck(BaseModel):
    __tablename__ = "flashcard_decks"

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    topic_tag = Column(Enum(TopicTag, name="topic_tag_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]), nullable=True)
    level = Column(Enum(DeckLevel, name="deck_level_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]), nullable=True)
    is_public = Column(Boolean, default=False, nullable=False)
    card_count = Column(Integer, default=0, nullable=False)
    cover_image_url = Column(String(500), nullable=True)

    class_id = Column(PG_UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=True)

    cards = relationship("Flashcard", back_populates="deck", cascade="all, delete-orphan")


class Flashcard(BaseModel):
    __tablename__ = "flashcards"
    __table_args__ = (
        UniqueConstraint("deck_id", "word", name="uq_flashcard_word_deck"),
    )

    deck_id = Column(PG_UUID(as_uuid=True), ForeignKey("flashcard_decks.id", ondelete="CASCADE"), nullable=False)
    word = Column(String(200), nullable=False)
    ipa = Column(String(200), nullable=True)
    word_type = Column(Enum(WordType, name="word_type_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]), nullable=True)
    definition_en = Column(Text, nullable=True)
    definition_vi = Column(Text, nullable=True)
    example_sentence = Column(Text, nullable=True)
    audio_url = Column(String(500), nullable=True)
    source_vocabulary_id = Column(PG_UUID(as_uuid=True), ForeignKey("user_vocabulary.id", ondelete="SET NULL"), nullable=True)

    deck = relationship("FlashcardDeck", back_populates="cards")
    reviews = relationship("FlashcardReview", back_populates="card", cascade="all, delete-orphan")


class FlashcardReview(BaseModel):
    __tablename__ = "flashcard_reviews"
    __table_args__ = (
        Index("idx_review_user_due", "user_id", "due_date"),
        Index("uq_review_user_card", "user_id", "card_id", unique=True, postgresql_where=Column("deleted_at").is_(None)),
    )

    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    card_id = Column(PG_UUID(as_uuid=True), ForeignKey("flashcards.id", ondelete="CASCADE"), nullable=False)

    state = Column(Enum(ReviewState, name="review_state_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]), default=ReviewState.NEW, nullable=False)
    stability = Column(Float, nullable=False, default=0.0)
    difficulty = Column(Float, nullable=False, default=0.0)
    retrievability = Column(Float, nullable=True)
    
    repetition_count = Column(Integer, default=0, nullable=False)
    lapses = Column(Integer, default=0, nullable=False)
    
    last_review_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    last_rating = Column(Enum(Rating, name="review_rating_enum", native_enum=False, values_callable=lambda x: [e.value for e in x]), nullable=True)

    card = relationship("Flashcard", back_populates="reviews")
