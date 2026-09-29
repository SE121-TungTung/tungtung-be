"""
Repositories: Flashcard
Covers: FlashcardDeckRepository, FlashcardRepository, FlashcardReviewRepository
"""
from typing import Optional, List, Tuple
from uuid import UUID
from datetime import datetime, timezone, timedelta, date

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.repositories.base import BaseRepository
from app.models.flashcard import (
    FlashcardDeck, Flashcard, FlashcardReview,
    TopicTag, DeckLevel, ReviewState, Rating
)


# ---------------------------------------------------------------------------
# FlashcardDeckRepository
# ---------------------------------------------------------------------------

class FlashcardDeckRepository(BaseRepository[FlashcardDeck]):
    def __init__(self):
        super().__init__(FlashcardDeck)

    def get_by_id(self, db: Session, deck_id: UUID) -> Optional[FlashcardDeck]:
        return (
            db.query(FlashcardDeck)
            .filter(FlashcardDeck.id == deck_id, FlashcardDeck.deleted_at.is_(None))
            .first()
        )

    def get_list(
        self,
        db: Session,
        user_id: UUID,
        topic_tag: Optional[TopicTag] = None,
        level: Optional[DeckLevel] = None,
        is_public: Optional[bool] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[FlashcardDeck], int]:
        """Lấy list decks: deck public HOẶC deck do chính user tạo."""
        query = db.query(FlashcardDeck).filter(
            FlashcardDeck.deleted_at.is_(None),
            or_(
                FlashcardDeck.is_public == True,
                FlashcardDeck.created_by == user_id,
            )
        )

        if topic_tag is not None:
            query = query.filter(FlashcardDeck.topic_tag == topic_tag.value)
        if level is not None:
            query = query.filter(FlashcardDeck.level == level.value)
        if is_public is not None:
            query = query.filter(FlashcardDeck.is_public == is_public)

        total = query.count()
        items = (
            query
            .order_by(FlashcardDeck.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    def soft_delete(self, db: Session, deck: FlashcardDeck) -> None:
        deck.deleted_at = datetime.now(timezone.utc)
        db.commit()

    def increment_card_count(self, db: Session, deck: FlashcardDeck, delta: int = 1) -> None:
        deck.card_count = max(0, (deck.card_count or 0) + delta)
        db.commit()


# ---------------------------------------------------------------------------
# FlashcardRepository
# ---------------------------------------------------------------------------

class FlashcardRepository(BaseRepository[Flashcard]):
    def __init__(self):
        super().__init__(Flashcard)

    def get_by_id(self, db: Session, card_id: UUID) -> Optional[Flashcard]:
        return (
            db.query(Flashcard)
            .filter(Flashcard.id == card_id, Flashcard.deleted_at.is_(None))
            .first()
        )

    def get_by_deck(
        self,
        db: Session,
        deck_id: UUID,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[Flashcard], int]:
        query = db.query(Flashcard).filter(
            Flashcard.deck_id == deck_id,
            Flashcard.deleted_at.is_(None),
        )
        total = query.count()
        items = (
            query
            .order_by(Flashcard.created_at.asc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    def check_word_exists(self, db: Session, deck_id: UUID, word: str, exclude_id: Optional[UUID] = None) -> bool:
        """Kiểm tra xem từ đã tồn tại trong deck chưa (trừ card đang edit)."""
        q = db.query(Flashcard).filter(
            Flashcard.deck_id == deck_id,
            Flashcard.word == word.strip(),
            Flashcard.deleted_at.is_(None),
        )
        if exclude_id:
            q = q.filter(Flashcard.id != exclude_id)
        return q.first() is not None

    def soft_delete(self, db: Session, card: Flashcard) -> None:
        card.deleted_at = datetime.now(timezone.utc)
        db.commit()

    def bulk_create(self, db: Session, cards_data: List[dict]) -> List[Flashcard]:
        """Tạo nhiều card cùng lúc (dùng cho import)."""
        created = []
        for data in cards_data:
            card = Flashcard(**data)
            db.add(card)
            created.append(card)
        db.flush()
        for c in created:
            db.refresh(c)
        db.commit()
        return created


# ---------------------------------------------------------------------------
# FlashcardReviewRepository
# ---------------------------------------------------------------------------

class FlashcardReviewRepository(BaseRepository[FlashcardReview]):
    def __init__(self):
        super().__init__(FlashcardReview)

    def get_by_user_and_card(
        self, db: Session, user_id: UUID, card_id: UUID
    ) -> Optional[FlashcardReview]:
        return (
            db.query(FlashcardReview)
            .filter(
                FlashcardReview.user_id == user_id,
                FlashcardReview.card_id == card_id,
                FlashcardReview.deleted_at.is_(None),
            )
            .first()
        )

    def upsert(self, db: Session, user_id: UUID, card_id: UUID, update_data: dict) -> FlashcardReview:
        """
        Nếu bản ghi đã tồn tại thì update, chưa có thì insert.
        Không dùng ON CONFLICT vì vướng partial unique index.
        """
        existing = self.get_by_user_and_card(db, user_id, card_id)
        if existing:
            for k, v in update_data.items():
                setattr(existing, k, v)
            existing.deleted_at = None
            db.commit()
            db.refresh(existing)
            return existing
        else:
            import uuid as _uuid
            new_review = FlashcardReview(
                id=_uuid.uuid4(),
                user_id=user_id,
                card_id=card_id,
                **update_data
            )
            db.add(new_review)
            db.commit()
            db.refresh(new_review)
            return new_review

    def get_due_cards(
        self,
        db: Session,
        user_id: UUID,
        deck_id: Optional[UUID] = None,
        limit: int = 20,
    ) -> List[FlashcardReview]:
        """
        Lấy tối đa `limit` bản ghi FlashcardReview cần ôn:
        - state = 'new' (chưa từng học)
        - HOẶC due_date <= now() (đến hạn)
        Kết quả ORDER BY due_date ASC (NULL first cho thẻ mới).
        """
        now = datetime.now(timezone.utc)

        query = (
            db.query(FlashcardReview)
            .join(Flashcard, Flashcard.id == FlashcardReview.card_id)
            .filter(
                FlashcardReview.user_id == user_id,
                FlashcardReview.deleted_at.is_(None),
                Flashcard.deleted_at.is_(None),
                or_(
                    FlashcardReview.state == ReviewState.NEW.value,
                    FlashcardReview.due_date <= now,
                ),
            )
        )

        if deck_id:
            query = query.filter(Flashcard.deck_id == deck_id)

        return (
            query
            .order_by(FlashcardReview.due_date.asc().nullsfirst())
            .limit(limit)
            .all()
        )

    def get_new_cards_for_deck(
        self, db: Session, user_id: UUID, deck_id: UUID, limit: int = 20
    ) -> List[Flashcard]:
        """
        Lấy những thẻ trong deck mà user CHƯA có FlashcardReview record nào
        (thẻ hoàn toàn mới, chưa từng study).
        """
        reviewed_card_ids = (
            db.query(FlashcardReview.card_id)
            .filter(
                FlashcardReview.user_id == user_id,
                FlashcardReview.deleted_at.is_(None),
            )
            .subquery()
        )

        return (
            db.query(Flashcard)
            .filter(
                Flashcard.deck_id == deck_id,
                Flashcard.deleted_at.is_(None),
                ~Flashcard.id.in_(reviewed_card_ids),
            )
            .order_by(Flashcard.created_at.asc())
            .limit(limit)
            .all()
        )

    # ---- Stats helpers ----

    def get_daily_activity(
        self, db: Session, user_id: UUID, days: int = 30
    ) -> List[dict]:
        """Số thẻ review theo ngày trong `days` ngày gần nhất."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        rows = (
            db.query(
                func.date(FlashcardReview.updated_at).label("day"),
                func.count(FlashcardReview.id).label("count"),
            )
            .filter(
                FlashcardReview.user_id == user_id,
                FlashcardReview.last_review_date >= cutoff,
                FlashcardReview.deleted_at.is_(None),
            )
            .group_by(func.date(FlashcardReview.updated_at))
            .order_by(func.date(FlashcardReview.updated_at))
            .all()
        )
        return [{"date": row.day, "count": row.count} for row in rows]

    def get_total_reviews(self, db: Session, user_id: UUID) -> int:
        return (
            db.query(func.sum(FlashcardReview.repetition_count))
            .filter(
                FlashcardReview.user_id == user_id,
                FlashcardReview.deleted_at.is_(None),
            )
            .scalar()
        ) or 0

    def get_total_mastered(self, db: Session, user_id: UUID) -> int:
        """State = 'review' và đã review ít nhất 3 lần = thuộc."""
        return (
            db.query(FlashcardReview)
            .filter(
                FlashcardReview.user_id == user_id,
                FlashcardReview.state == ReviewState.REVIEW.value,
                FlashcardReview.repetition_count >= 3,
                FlashcardReview.deleted_at.is_(None),
            )
            .count()
        )

    def get_due_count_for_deck(self, db: Session, user_id: UUID, deck_id: UUID) -> int:
        """Đếm số thẻ đến hạn trong một deck cụ thể."""
        now = datetime.now(timezone.utc)
        existing_due = (
            db.query(FlashcardReview)
            .join(Flashcard, Flashcard.id == FlashcardReview.card_id)
            .filter(
                FlashcardReview.user_id == user_id,
                FlashcardReview.deleted_at.is_(None),
                Flashcard.deck_id == deck_id,
                Flashcard.deleted_at.is_(None),
                or_(
                    FlashcardReview.state == ReviewState.NEW.value,
                    FlashcardReview.due_date <= now,
                ),
            )
            .count()
        )
        # Cộng thêm thẻ hoàn toàn mới (chưa có review record)
        new_cards_count = (
            db.query(Flashcard)
            .filter(
                Flashcard.deck_id == deck_id,
                Flashcard.deleted_at.is_(None),
                ~Flashcard.id.in_(
                    db.query(FlashcardReview.card_id).filter(
                        FlashcardReview.user_id == user_id,
                        FlashcardReview.deleted_at.is_(None),
                    )
                ),
            )
            .count()
        )
        return existing_due + new_cards_count


# Singleton instances
flashcard_deck_repo = FlashcardDeckRepository()
flashcard_card_repo = FlashcardRepository()
flashcard_review_repo = FlashcardReviewRepository()
