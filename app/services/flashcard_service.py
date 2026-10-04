"""
Services: Flashcard
Covers:
  - FlashcardDeckService    (CRUD + author guard)
  - FlashcardReviewService  (FSRS engine integration)
  - FlashcardStatsService   (streak, heatmap, mastered count)
"""
from typing import Optional, List, Tuple
from uuid import UUID
from datetime import datetime, timezone, date, timedelta

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import APIException
from app.models.flashcard import (
    FlashcardDeck, Flashcard, FlashcardReview,
    ReviewState, Rating
)
from app.models.vocabulary import UserVocabulary
from app.repositories.flashcard import (
    flashcard_deck_repo, flashcard_card_repo, flashcard_review_repo
)
from app.schemas.flashcard import (
    FlashcardDeckCreate, FlashcardDeckUpdate,
    FlashcardCreate, FlashcardUpdate,
    ReviewSubmitRequest,
    ImportFromVocabularyRequest,
)
from app.services.fsrs_engine import FSRSEngine

_fsrs = FSRSEngine()


# ---------------------------------------------------------------------------
# FlashcardDeckService
# ---------------------------------------------------------------------------

class FlashcardDeckService:

    # ---- READ ----

    async def get_list(
        self,
        db: Session,
        user_id: UUID,
        topic_tag=None,
        level=None,
        is_public=None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[FlashcardDeck], int]:
        return flashcard_deck_repo.get_list(
            db, user_id=user_id,
            topic_tag=topic_tag, level=level,
            is_public=is_public, page=page, limit=limit,
        )

    async def get_detail(self, db: Session, deck_id: UUID) -> FlashcardDeck:
        deck = flashcard_deck_repo.get_by_id(db, deck_id)
        if not deck:
            raise APIException(status_code=404, code="DECK_NOT_FOUND", message="Flashcard deck not found.")
        return deck

    # ---- CREATE ----

    async def create_deck(
        self, db: Session, user_id: UUID, payload: FlashcardDeckCreate
    ) -> FlashcardDeck:
        data = payload.model_dump(exclude_none=False)
        # Convert enum to string value for DB
        if data.get("topic_tag") is not None:
            data["topic_tag"] = data["topic_tag"].value
        if data.get("level") is not None:
            data["level"] = data["level"].value
        data["created_by"] = user_id
        data["updated_by"] = user_id
        data["card_count"] = 0
        return flashcard_deck_repo.create(db, data)

    # ---- UPDATE ----

    async def update_deck(
        self, db: Session, deck_id: UUID, user_id: UUID, payload: FlashcardDeckUpdate
    ) -> FlashcardDeck:
        deck = await self.get_detail(db, deck_id)
        self._check_author(deck, user_id)

        update_data = payload.model_dump(exclude_unset=True)
        if "topic_tag" in update_data and update_data["topic_tag"] is not None:
            update_data["topic_tag"] = update_data["topic_tag"].value
        if "level" in update_data and update_data["level"] is not None:
            update_data["level"] = update_data["level"].value
        update_data["updated_by"] = user_id
        return flashcard_deck_repo.update(db, deck, update_data)

    # ---- DELETE ----

    async def soft_delete_deck(
        self, db: Session, deck_id: UUID, user_id: UUID
    ) -> None:
        deck = await self.get_detail(db, deck_id)
        self._check_author(deck, user_id)
        flashcard_deck_repo.soft_delete(db, deck)

    # ---- GUARD ----

    def _check_author(self, deck: FlashcardDeck, user_id: UUID) -> None:
        """Chỉ người tạo (hoặc admin) mới được sửa/xóa."""
        if deck.created_by != user_id:
            raise APIException(
                status_code=403,
                code="DECK_FORBIDDEN",
                message="You do not have permission to modify this deck.",
            )


# ---------------------------------------------------------------------------
# FlashcardCardService
# ---------------------------------------------------------------------------

class FlashcardCardService:

    async def get_cards(
        self, db: Session, deck_id: UUID, page: int = 1, limit: int = 50
    ) -> Tuple[List[Flashcard], int]:
        # Validate deck exists
        deck = flashcard_deck_repo.get_by_id(db, deck_id)
        if not deck:
            raise APIException(status_code=404, code="DECK_NOT_FOUND", message="Flashcard deck not found.")
        return flashcard_card_repo.get_by_deck(db, deck_id, page=page, limit=limit)

    async def create_card(
        self, db: Session, deck_id: UUID, user_id: UUID, payload: FlashcardCreate
    ) -> Flashcard:
        deck = flashcard_deck_repo.get_by_id(db, deck_id)
        if not deck:
            raise APIException(status_code=404, code="DECK_NOT_FOUND", message="Flashcard deck not found.")

        # Unique check
        if flashcard_card_repo.check_word_exists(db, deck_id, payload.word):
            raise APIException(
                status_code=409,
                code="CARD_DUPLICATE",
                message=f"Word '{payload.word}' already exists in this deck.",
            )

        data = payload.model_dump(exclude_none=False)
        if data.get("word_type") is not None:
            data["word_type"] = data["word_type"].value
        data["deck_id"] = deck_id
        data["created_by"] = user_id
        data["updated_by"] = user_id
        data["word"] = payload.word.strip()

        try:
            card = flashcard_card_repo.create(db, data)
        except IntegrityError:
            db.rollback()
            raise APIException(
                status_code=409,
                code="CARD_DUPLICATE",
                message=f"Word '{payload.word}' already exists in this deck.",
            )

        # Update card_count
        flashcard_deck_repo.increment_card_count(db, deck, delta=1)
        return card

    async def update_card(
        self, db: Session, deck_id: UUID, card_id: UUID, user_id: UUID, payload: FlashcardUpdate
    ) -> Flashcard:
        card = flashcard_card_repo.get_by_id(db, card_id)
        if not card or card.deck_id != deck_id:
            raise APIException(status_code=404, code="CARD_NOT_FOUND", message="Flashcard not found in this deck.")

        update_data = payload.model_dump(exclude_unset=True)
        # Unique word check if word is changing
        if "word" in update_data:
            new_word = update_data["word"].strip()
            if flashcard_card_repo.check_word_exists(db, deck_id, new_word, exclude_id=card_id):
                raise APIException(
                    status_code=409,
                    code="CARD_DUPLICATE",
                    message=f"Word '{new_word}' already exists in this deck.",
                )
            update_data["word"] = new_word
        if "word_type" in update_data and update_data["word_type"] is not None:
            update_data["word_type"] = update_data["word_type"].value
        update_data["updated_by"] = user_id

        return flashcard_card_repo.update(db, card, update_data)

    async def soft_delete_card(
        self, db: Session, deck_id: UUID, card_id: UUID, user_id: UUID
    ) -> None:
        card = flashcard_card_repo.get_by_id(db, card_id)
        if not card or card.deck_id != deck_id:
            raise APIException(status_code=404, code="CARD_NOT_FOUND", message="Flashcard not found in this deck.")

        deck = flashcard_deck_repo.get_by_id(db, deck_id)
        flashcard_card_repo.soft_delete(db, card)
        if deck:
            flashcard_deck_repo.increment_card_count(db, deck, delta=-1)

    async def import_from_vocabulary(
        self, db: Session, user_id: UUID, payload: ImportFromVocabularyRequest
    ) -> Tuple[int, int]:
        """
        Import từ user_vocabulary vào deck.
        Returns: (success_count, skipped_count)
        """
        deck = flashcard_deck_repo.get_by_id(db, payload.deck_id)
        if not deck:
            raise APIException(status_code=404, code="DECK_NOT_FOUND", message="Flashcard deck not found.")

        vocab_items = (
            db.query(UserVocabulary)
            .filter(
                UserVocabulary.id.in_(payload.vocabulary_ids),
                UserVocabulary.user_id == user_id,
            )
            .all()
        )

        cards_to_create = []
        skipped = 0
        for vocab in vocab_items:
            if flashcard_card_repo.check_word_exists(db, payload.deck_id, vocab.word):
                skipped += 1
                continue
            cards_to_create.append({
                "deck_id": payload.deck_id,
                "word": vocab.word,
                "ipa": vocab.ipa,
                "definition_vi": vocab.meaning_vi,
                "example_sentence": vocab.example,
                "word_type": vocab.word_type,
                "source_vocabulary_id": vocab.id,
                "created_by": user_id,
                "updated_by": user_id,
            })

        if cards_to_create:
            flashcard_card_repo.bulk_create(db, cards_to_create)
            flashcard_deck_repo.increment_card_count(db, deck, delta=len(cards_to_create))

        return len(cards_to_create), skipped


# ---------------------------------------------------------------------------
# FlashcardReviewService
# ---------------------------------------------------------------------------

class FlashcardReviewService:

    async def get_due_cards(
        self, db: Session, user_id: UUID, deck_id: Optional[UUID] = None, limit: int = 20
    ) -> List[dict]:
        """
        Lấy tối đa `limit` thẻ cần ôn hôm nay.
        Bao gồm: thẻ có review record (state=NEW or due_date<=now)
                 + thẻ chưa có review record nào (hoàn toàn mới).
        """
        # Bước 1: Thẻ có review record đến hạn
        review_records = flashcard_review_repo.get_due_cards(
            db, user_id=user_id, deck_id=deck_id, limit=limit
        )
        result = []
        seen_card_ids = set()

        for review in review_records:
            card = flashcard_card_repo.get_by_id(db, review.card_id)
            if card:
                result.append({"card": card, "review": review})
                seen_card_ids.add(review.card_id)

        # Bước 2: Nếu còn chỗ, thêm thẻ chưa từng học
        remaining = limit - len(result)
        if remaining > 0:
            if deck_id:
                new_cards = flashcard_review_repo.get_new_cards_for_deck(
                    db, user_id=user_id, deck_id=deck_id, limit=remaining
                )
                for card in new_cards:
                    if card.id not in seen_card_ids:
                        result.append({"card": card, "review": None})
            else:
                # Nếu không filter theo deck, lấy thẻ mới từ tất cả các deck public/sở hữu
                from app.repositories.flashcard import flashcard_deck_repo as _deck_repo
                decks, _ = _deck_repo.get_list(db, user_id=user_id, page=1, limit=100)
                for deck in decks:
                    if remaining <= 0:
                        break
                    new_cards = flashcard_review_repo.get_new_cards_for_deck(
                        db, user_id=user_id, deck_id=deck.id, limit=remaining
                    )
                    for card in new_cards:
                        if card.id not in seen_card_ids and remaining > 0:
                            result.append({"card": card, "review": None})
                            seen_card_ids.add(card.id)
                            remaining -= 1

        return result

    async def submit_review(
        self,
        db: Session,
        user_id: UUID,
        payload: ReviewSubmitRequest,
    ) -> FlashcardReview:
        """Submit rating → FSRSEngine → upsert FlashcardReview."""
        card = flashcard_card_repo.get_by_id(db, payload.card_id)
        if not card:
            raise APIException(status_code=404, code="CARD_NOT_FOUND", message="Flashcard not found.")

        existing = flashcard_review_repo.get_by_user_and_card(db, user_id, payload.card_id)
        now = datetime.now(timezone.utc)

        # Lấy state hiện tại
        if existing:
            current_state = ReviewState(existing.state)
            current_stability = existing.stability
            current_difficulty = existing.difficulty
            current_retrievability = existing.retrievability or 0.0
            current_lapses = existing.lapses
            current_reps = existing.repetition_count
            last_review = existing.last_review_date
        else:
            current_state = ReviewState.NEW
            current_stability = 0.0
            current_difficulty = 0.0
            current_retrievability = 0.0
            current_lapses = 0
            current_reps = 0
            last_review = None

        rating_enum = payload.to_rating_enum()

        # Chạy FSRSEngine
        new_state, new_s, new_d, new_r, new_lapses, new_reps, due_date = _fsrs.calculate_next_review(
            rating=rating_enum,
            state=current_state,
            stability=current_stability,
            difficulty=current_difficulty,
            retrievability=current_retrievability,
            lapses=current_lapses,
            reps=current_reps,
            last_review_date=last_review,
            now=now,
        )

        update_data = {
            "state": new_state,
            "stability": new_s,
            "difficulty": new_d,
            "retrievability": new_r,
            "repetition_count": new_reps,
            "lapses": new_lapses,
            "last_review_date": now,
            "due_date": due_date,
            "last_rating": rating_enum,
        }

        return flashcard_review_repo.upsert(db, user_id=user_id, card_id=payload.card_id, update_data=update_data)


# ---------------------------------------------------------------------------
# FlashcardStatsService
# ---------------------------------------------------------------------------

class FlashcardStatsService:

    async def get_stats(self, db: Session, user_id: UUID) -> dict:
        daily_activity = flashcard_review_repo.get_daily_activity(db, user_id, days=30)
        total_reviews = flashcard_review_repo.get_total_reviews(db, user_id)
        total_mastered = flashcard_review_repo.get_total_mastered(db, user_id)

        now = datetime.now(timezone.utc)
        due_today = len(flashcard_review_repo.get_due_cards(db, user_id=user_id, limit=9999))

        streak_days = self._calculate_streak(daily_activity)

        return {
            "total_reviews": total_reviews,
            "total_mastered": total_mastered,
            "streak_days": streak_days,
            "due_today": due_today,
            "heatmap": daily_activity,
        }

    def _calculate_streak(self, daily_activity: List[dict]) -> int:
        """Tính số ngày liên tiếp ôn bài (tính từ hôm qua trở về trước)."""
        if not daily_activity:
            return 0

        activity_dates = {row["date"] for row in daily_activity}
        today = date.today()
        streak = 0

        # Bắt đầu kiểm tra từ hôm qua (hôm nay chưa chắc đã ôn)
        check_date = today - timedelta(days=1)
        # Nếu hôm nay đã có hoạt động thì tính cả hôm nay
        if today in activity_dates:
            check_date = today

        while check_date in activity_dates:
            streak += 1
            check_date -= timedelta(days=1)

        return streak


# Singleton instances
flashcard_deck_service = FlashcardDeckService()
flashcard_card_service = FlashcardCardService()
flashcard_review_service = FlashcardReviewService()
flashcard_stats_service = FlashcardStatsService()
