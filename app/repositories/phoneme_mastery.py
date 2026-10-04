"""
Repository: Pronunciation Phoneme Mastery + Assessments
Bao gồm SM-2 Spaced Repetition update logic.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_

from app.models.pronunciation import (
    PronunciationPhonemeMastery,
    PronunciationAssessment,
)
from app.repositories.base import BaseRepository


class PhonemeMasteryRepository(BaseRepository[PronunciationPhonemeMastery]):
    def __init__(self):
        super().__init__(PronunciationPhonemeMastery)

    def get_or_create(
        self, db: Session, student_id: UUID, phoneme: str
    ) -> PronunciationPhonemeMastery:
        """Lấy hoặc tạo mới record mastery cho 1 phoneme của 1 student."""
        existing = (
            db.query(self.model)
            .filter(
                self.model.student_id == student_id,
                self.model.phoneme == phoneme,
                self.model.deleted_at.is_(None),
            )
            .first()
        )
        if existing:
            return existing

        mastery = self.model(
            student_id=student_id,
            phoneme=phoneme,
            mastery_level=0,
            created_by=student_id,
        )
        db.add(mastery)
        db.flush()
        return mastery

    def update_after_practice(
        self,
        db: Session,
        student_id: UUID,
        phoneme: str,
        score: float,
    ) -> PronunciationPhonemeMastery:
        """
        Cập nhật mastery + SM-2 sau mỗi lần luyện tập.

        Args:
            score: 0.0 - 100.0 (overall phoneme accuracy)
        """
        mastery = self.get_or_create(db, student_id, phoneme)

        # Update attempt stats
        mastery.total_attempts += 1
        is_correct = score >= 70.0
        if is_correct:
            mastery.correct_attempts += 1
        mastery.last_score = score
        mastery.last_practiced_at = datetime.utcnow()

        # ── SM-2 Algorithm ──
        # Map score 0-100 → SM-2 quality 0-5
        quality = min(5, max(0, round(score / 20)))  # 0→fail, 3→pass, 5→perfect

        if quality < 3:
            # Fail → reset repetition, review tomorrow
            mastery.repetition_count = 0
            mastery.interval_days = 1
        else:
            # Pass → increase interval
            if mastery.repetition_count == 0:
                mastery.interval_days = 1
            elif mastery.repetition_count == 1:
                mastery.interval_days = 6
            else:
                mastery.interval_days = max(
                    1,
                    round(int(mastery.interval_days) * float(mastery.easiness_factor)),
                )
            mastery.repetition_count += 1

        # Update Easiness Factor: EF' = EF + (0.1 - (5-q)*(0.08+(5-q)*0.02))
        ef = float(mastery.easiness_factor)
        ef = ef + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        mastery.easiness_factor = max(1.3, round(ef, 2))

        # Schedule next review
        mastery.next_review_at = datetime.utcnow() + timedelta(
            days=mastery.interval_days
        )

        # Compute rolling 7-day average from last_score (simplified: use EMA)
        if mastery.avg_score_7d is None:
            mastery.avg_score_7d = score
        else:
            alpha = 0.3  # Exponential moving average weight
            mastery.avg_score_7d = round(
                alpha * score + (1 - alpha) * float(mastery.avg_score_7d), 2
            )

        # Update mastery_level based on avg_score_7d
        avg = float(mastery.avg_score_7d)
        if avg >= 85:
            mastery.mastery_level = 4  # Mastered
        elif avg >= 70:
            mastery.mastery_level = 3  # Practiced
        elif avg >= 50:
            mastery.mastery_level = 2  # Familiar
        elif mastery.total_attempts > 0:
            mastery.mastery_level = 1  # Learning
        else:
            mastery.mastery_level = 0  # Unseen

        mastery.updated_by = student_id
        db.flush()
        return mastery

    def batch_update_from_phoneme_results(
        self,
        db: Session,
        student_id: UUID,
        phoneme_results: list,
    ) -> List[PronunciationPhonemeMastery]:
        """
        Batch update mastery cho tất cả phonemes trong kết quả 1 lần luyện tập.
        Trích xuất phoneme + is_correct + confidence từ DTW results.
        """
        updated = []
        # Gom score theo phoneme
        phoneme_scores: Dict[str, list] = {}
        for r in phoneme_results:
            ph = r.get("phoneme_expected")
            if not ph:
                continue
            conf = r.get("confidence", 0.0)
            is_correct = r.get("is_correct", False)
            score = conf * 100 if is_correct else conf * 50
            phoneme_scores.setdefault(ph, []).append(score)

        for phoneme, scores in phoneme_scores.items():
            avg_score = sum(scores) / len(scores)
            mastery = self.update_after_practice(
                db, student_id, phoneme, avg_score
            )
            updated.append(mastery)

        db.commit()
        return updated

    def get_student_mastery_all(
        self, db: Session, student_id: UUID
    ) -> List[PronunciationPhonemeMastery]:
        """Lấy tất cả mastery records của 1 student."""
        return (
            db.query(self.model)
            .filter(
                self.model.student_id == student_id,
                self.model.deleted_at.is_(None),
            )
            .order_by(self.model.phoneme)
            .all()
        )

    def get_due_for_review(
        self, db: Session, student_id: UUID, limit: int = 10
    ) -> List[PronunciationPhonemeMastery]:
        """Lấy phonemes cần ôn tập (next_review_at <= now), ưu tiên mastery thấp."""
        now = datetime.utcnow()
        return (
            db.query(self.model)
            .filter(
                self.model.student_id == student_id,
                self.model.deleted_at.is_(None),
                self.model.next_review_at <= now,
                self.model.total_attempts > 0,  # chỉ lấy phoneme đã luyện
            )
            .order_by(self.model.mastery_level.asc(), self.model.next_review_at.asc())
            .limit(limit)
            .all()
        )

    def get_mastery_summary(
        self, db: Session, student_id: UUID
    ) -> Dict[str, Any]:
        """Tổng hợp mastery theo category cho Radar Chart."""
        all_mastery = self.get_student_mastery_all(db, student_id)

        PHONEME_CATEGORIES = {
            "Stops": {"p", "b", "t", "d", "k", "g", "ɡ", "ʔ"},
            "Fricatives": {"f", "v", "θ", "ð", "s", "z", "ʃ", "ʒ", "h"},
            "Affricates": {"tʃ", "dʒ"},
            "Nasals": {"m", "n", "ŋ"},
            "Approximants": {"l", "r", "ɹ", "j", "w"},
            "Short Vowels": {"ɪ", "ɛ", "e", "æ", "ʌ", "ɒ", "ʊ", "ə"},
            "Long Vowels": {"iː", "ɑː", "ɔː", "uː", "ɜː"},
            "Diphthongs": {"eɪ", "aɪ", "ɔɪ", "aʊ", "oʊ", "ɪə", "eə", "ʊə"},
        }

        category_scores: Dict[str, Dict[str, Any]] = {}
        mastery_map = {m.phoneme: m for m in all_mastery}

        for cat_name, phonemes in PHONEME_CATEGORIES.items():
            scores = []
            for ph in phonemes:
                m = mastery_map.get(ph)
                if m and m.avg_score_7d is not None:
                    scores.append(float(m.avg_score_7d))
            category_scores[cat_name] = {
                "avg_mastery": round(sum(scores) / len(scores), 1) if scores else 0,
                "practiced_count": len(scores),
                "total_phonemes": len(phonemes),
            }

        # Overall stats
        total_mastered = sum(1 for m in all_mastery if m.mastery_level >= 4)
        total_learning = sum(1 for m in all_mastery if 1 <= m.mastery_level <= 3)
        total_unseen = 44 - len(all_mastery)  # 44 IPA phonemes total

        return {
            "categories": category_scores,
            "total_mastered": total_mastered,
            "total_learning": total_learning,
            "total_unseen": max(0, total_unseen),
            "due_for_review_count": (
                db.query(func.count(self.model.id))
                .filter(
                    self.model.student_id == student_id,
                    self.model.deleted_at.is_(None),
                    self.model.next_review_at <= datetime.utcnow(),
                    self.model.total_attempts > 0,
                )
                .scalar()
                or 0
            ),
        }


class AssessmentRepository(BaseRepository[PronunciationAssessment]):
    def __init__(self):
        super().__init__(PronunciationAssessment)

    def create_assessment(
        self, db: Session, data: dict
    ) -> PronunciationAssessment:
        """Lưu kết quả placement test."""
        assessment = self.model(**data)
        db.add(assessment)
        db.commit()
        db.refresh(assessment)
        return assessment

    def get_latest(
        self, db: Session, student_id: UUID
    ) -> Optional[PronunciationAssessment]:
        """Lấy kết quả assessment gần nhất của student."""
        return (
            db.query(self.model)
            .filter(
                self.model.student_id == student_id,
                self.model.deleted_at.is_(None),
            )
            .order_by(desc(self.model.created_at))
            .first()
        )

    def get_all_for_student(
        self, db: Session, student_id: UUID
    ) -> List[PronunciationAssessment]:
        """Lấy lịch sử tất cả assessments."""
        return (
            db.query(self.model)
            .filter(
                self.model.student_id == student_id,
                self.model.deleted_at.is_(None),
            )
            .order_by(desc(self.model.created_at))
            .all()
        )


phoneme_mastery_repository = PhonemeMasteryRepository()
assessment_repository = AssessmentRepository()
