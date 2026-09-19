"""
Service: VocabularyService
Spec ref: ielts_system_spec_part2.md § 4.2
"""
from typing import Optional, List, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.vocabulary import UserVocabulary
from app.schemas.vocabulary import VocabularySaveRequest, VocabularyUpdateRequest
from app.core.exceptions import APIException


class VocabularyService:
    """CRUD nghiệp vụ cho sổ tay từ vựng cá nhân của học viên."""

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    async def save_word(
        self,
        db: Session,
        user_id: UUID,
        payload: VocabularySaveRequest,
    ) -> UserVocabulary:
        """
        Lưu 1 từ vào sổ tay.
        - Nếu (user_id, word, source_passage_id) đã tồn tại → raise 409 CONFLICT.
        """
        entry = UserVocabulary(
            user_id=user_id,
            word=payload.word.strip(),
            ipa=payload.ipa,
            meaning_vi=payload.meaning_vi,
            example=payload.example,
            word_type=payload.word_type,
            source_passage_id=payload.source_passage_id,
            mastery_level=0,
        )
        db.add(entry)
        try:
            db.commit()
            db.refresh(entry)
        except IntegrityError:
            db.rollback()
            raise APIException(
                status_code=409,
                code="VOCAB_DUPLICATE",
                message=f"Word '{payload.word}' already saved from this passage.",
            )
        return entry

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    async def get_my_words(
        self,
        db: Session,
        user_id: UUID,
        page: int = 1,
        limit: int = 20,
        mastery_level: Optional[int] = None,
        word_type: Optional[str] = None,
    ) -> Tuple[List[UserVocabulary], int]:
        """
        Lấy danh sách từ vựng của user với filter + pagination.
        Returns: (items, total_count)
        """
        query = (
            db.query(UserVocabulary)
            .filter(UserVocabulary.user_id == user_id)
        )

        if mastery_level is not None:
            query = query.filter(UserVocabulary.mastery_level == mastery_level)

        if word_type:
            query = query.filter(UserVocabulary.word_type == word_type)

        total = query.count()
        items = (
            query
            .order_by(UserVocabulary.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return items, total

    async def get_word_by_id(
        self,
        db: Session,
        vocab_id: UUID,
        user_id: UUID,
    ) -> UserVocabulary:
        """Lấy 1 từ theo id, đảm bảo thuộc về user hiện tại."""
        entry = (
            db.query(UserVocabulary)
            .filter(
                UserVocabulary.id == vocab_id,
                UserVocabulary.user_id == user_id,
            )
            .first()
        )
        if not entry:
            raise APIException(
                status_code=404,
                code="VOCAB_NOT_FOUND",
                message="Vocabulary entry not found.",
            )
        return entry

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    async def update_mastery(
        self,
        db: Session,
        vocab_id: UUID,
        user_id: UUID,
        payload: VocabularyUpdateRequest,
    ) -> UserVocabulary:
        """Cập nhật mastery_level của 1 từ."""
        entry = await self.get_word_by_id(db, vocab_id, user_id)
        entry.mastery_level = payload.mastery_level
        db.commit()
        db.refresh(entry)
        return entry

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    async def delete_word(
        self,
        db: Session,
        vocab_id: UUID,
        user_id: UUID,
    ) -> None:
        """Xoá 1 từ khỏi sổ tay."""
        entry = await self.get_word_by_id(db, vocab_id, user_id)
        db.delete(entry)
        db.commit()


# Singleton instance
vocabulary_service = VocabularyService()
