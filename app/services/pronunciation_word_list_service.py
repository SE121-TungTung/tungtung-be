"""
Service: Pronunciation Word List
Cầu nối giữa Flashcard và Pronunciation: thêm thẻ flashcard vào danh sách luyện phát âm,
kèm thống kê luyện tập theo từng từ.
"""
import logging
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import APIException
from app.models.pronunciation_word_list import PronunciationWordListItem, WordListSource
from app.repositories.flashcard import flashcard_card_repo
from app.repositories.pronunciation_word_list import pronunciation_word_list_repo
from app.schemas.pronunciation_word_list import (
    WordListAddRequest, WordListItemResponse, WordListResponse,
)
from app.services.dictionary_service import dictionary_service

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _infer_type(text: str) -> str:
    n = len(text.split())
    if n > 3:
        return "sentence"
    if n > 1:
        return "phrase"
    return "word"


class PronunciationWordListService:

    async def add(
        self, db: Session, student_id: UUID, payload: WordListAddRequest
    ) -> WordListItemResponse:
        text = (payload.target_text or "").strip()
        ipa = payload.ipa
        source = WordListSource.MANUAL
        card = None

        if payload.flashcard_id:
            card = flashcard_card_repo.get_by_id(db, payload.flashcard_id)
            if not card:
                raise APIException(
                    status_code=404, code="CARD_NOT_FOUND",
                    message="Flashcard not found.",
                )
            text = text or card.word.strip()
            ipa = ipa or card.ipa
            source = WordListSource.FLASHCARD

        if not text:
            raise APIException(
                status_code=422, code="WORD_LIST_TEXT_REQUIRED",
                message="target_text or flashcard_id is required.",
            )

        key = _normalize(text)
        existing = pronunciation_word_list_repo.get_by_key(db, student_id, key)
        if existing:
            # Idempotent: nếu trước đó thêm thủ công, gắn thêm liên kết flashcard
            if card and not existing.flashcard_id:
                existing.flashcard_id = card.id
                existing.source = WordListSource.FLASHCARD
                db.commit()
                db.refresh(existing)
            return self._to_response(db, student_id, [existing])[0]

        item = PronunciationWordListItem(
            student_id=student_id,
            target_text=text,
            text_key=key,
            target_type=payload.target_type or _infer_type(text),
            ipa=ipa,
            source=source,
            flashcard_id=card.id if card else None,
            created_by=student_id,
            updated_by=student_id,
        )
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = pronunciation_word_list_repo.get_by_key(db, student_id, key)
            if existing:
                return self._to_response(db, student_id, [existing])[0]
            raise
        db.refresh(item)
        responses = self._to_response(db, student_id, [item])
        await self._attach_ipa(db, responses)
        return responses[0]

    async def list(self, db: Session, student_id: UUID) -> WordListResponse:
        items, total = pronunciation_word_list_repo.list_by_student(db, student_id)
        responses = self._to_response(db, student_id, items)
        await self._attach_ipa(db, responses)
        return WordListResponse(items=responses, total=total)

    async def _attach_ipa(self, db: Session, responses: List[WordListItemResponse]) -> None:
        """Bổ sung IPA US/UK (cache DB -> dictionary API -> AI). Tối đa 20 mục/lần để giữ tốc độ."""
        if not responses:
            return
        batch = responses[:20]
        try:
            found = await dictionary_service.lookup_ipa_batch(db, [r.target_text for r in batch])
        except Exception:
            logger.exception("IPA enrichment failed for word list")
            return
        for resp, ipa in zip(batch, found):
            resp.ipa_us = ipa.get("ipa_us")
            resp.ipa_uk = ipa.get("ipa_uk")
            # IPA lưu của item chỉ dùng khi tra không ra
            if not resp.ipa_us and resp.ipa:
                resp.ipa_us = resp.ipa

    def remove(self, db: Session, student_id: UUID, item_id: UUID) -> None:
        item = pronunciation_word_list_repo.get_by_id(db, item_id, student_id)
        if not item:
            raise APIException(
                status_code=404, code="WORD_LIST_ITEM_NOT_FOUND",
                message="Word list item not found.",
            )
        pronunciation_word_list_repo.soft_delete(db, item)

    def _to_response(
        self, db: Session, student_id: UUID, items: List[PronunciationWordListItem]
    ) -> List[WordListItemResponse]:
        stats = pronunciation_word_list_repo.get_practice_stats_by_text(
            db, student_id, [i.text_key for i in items]
        )
        out: List[WordListItemResponse] = []
        for i in items:
            st = stats.get(i.text_key, {})
            out.append(WordListItemResponse(
                id=i.id,
                target_text=i.target_text,
                target_type=i.target_type,
                ipa=i.ipa,
                source=i.source.value if hasattr(i.source, "value") else i.source,
                flashcard_id=i.flashcard_id,
                deck_id=i.flashcard.deck_id if i.flashcard else None,
                created_at=i.created_at,
                practice_count=st.get("practice_count", 0),
                best_score=st.get("best_score"),
                last_score=st.get("last_score"),
                last_practiced_at=st.get("last_practiced_at"),
            ))
        return out


pronunciation_word_list_service = PronunciationWordListService()
