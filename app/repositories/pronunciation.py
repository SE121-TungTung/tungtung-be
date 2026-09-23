from typing import List, Optional, Tuple, Dict, Any
from uuid import UUID
from datetime import datetime, date, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_, cast, Date
from app.models.pronunciation import PronunciationPractice, TargetType
from app.repositories.base import BaseRepository


class PronunciationRepository(BaseRepository[PronunciationPractice]):
    def __init__(self):
        super().__init__(PronunciationPractice)

    def create_practice(self, db: Session, data: dict) -> PronunciationPractice:
        """Lưu kết quả lượt chấm phát âm."""
        practice = self.model(**data)
        db.add(practice)
        db.commit()
        db.refresh(practice)
        return practice

    def get_by_id(
        self, db: Session, practice_id: UUID, student_id: Optional[UUID] = None
    ) -> Optional[PronunciationPractice]:
        """Lấy chi tiết lượt luyện tập theo ID (có kiểm tra quyền sở hữu)."""
        query = db.query(self.model).filter(
            self.model.id == practice_id,
            self.model.deleted_at.is_(None),
        )
        if student_id:
            query = query.filter(self.model.student_id == student_id)
        return query.first()

    def get_student_practices(
        self,
        db: Session,
        student_id: UUID,
        target_type: Optional[TargetType] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[PronunciationPractice], int]:
        """Lấy danh sách lịch sử luyện tập có phân trang."""
        query = db.query(self.model).filter(
            self.model.student_id == student_id,
            self.model.deleted_at.is_(None),
        )
        if target_type:
            query = query.filter(self.model.target_type == target_type)

        total = query.count()
        items = (
            query.order_by(desc(self.model.created_at))
            .offset(skip)
            .limit(limit)
            .all()
        )
        return items, total

    def count_today_practices(self, db: Session, student_id: UUID) -> int:
        """Đếm số lượt luyện tập trong ngày hôm nay (UTC)."""
        today = datetime.utcnow().date()
        return (
            db.query(func.count(self.model.id))
            .filter(
                self.model.student_id == student_id,
                self.model.deleted_at.is_(None),
                cast(self.model.created_at, Date) == today,
            )
            .scalar()
            or 0
        )

    def get_student_stats(self, db: Session, student_id: UUID) -> Dict[str, Any]:
        """Tổng hợp thống kê luyện tập phát âm của học viên."""
        base_query = db.query(self.model).filter(
            self.model.student_id == student_id,
            self.model.deleted_at.is_(None),
        )

        # 1. Total practices and overall average score
        total = base_query.count()
        if total == 0:
            return {
                "total_practices": 0,
                "average_score": 0.0,
                "practice_by_type": {},
                "weak_phonemes": [],
                "recent_trend": [],
            }

        avg_score = (
            db.query(func.avg(self.model.overall_score))
            .filter(
                self.model.student_id == student_id,
                self.model.deleted_at.is_(None),
            )
            .scalar()
            or 0.0
        )

        # 2. Count by target_type
        type_counts = (
            db.query(self.model.target_type, func.count(self.model.id))
            .filter(
                self.model.student_id == student_id,
                self.model.deleted_at.is_(None),
            )
            .group_by(self.model.target_type)
            .all()
        )
        practice_by_type = {
            (t.value if hasattr(t, "value") else str(t)): count
            for t, count in type_counts
        }

        # 3. Recent trend: 14 days
        fourteen_days_ago = datetime.utcnow().date() - timedelta(days=14)
        trend_rows = (
            db.query(
                cast(self.model.created_at, Date).label("p_date"),
                func.avg(self.model.overall_score).label("avg_s"),
                func.count(self.model.id).label("cnt"),
            )
            .filter(
                self.model.student_id == student_id,
                self.model.deleted_at.is_(None),
                cast(self.model.created_at, Date) >= fourteen_days_ago,
            )
            .group_by(cast(self.model.created_at, Date))
            .order_by(cast(self.model.created_at, Date).asc())
            .all()
        )
        recent_trend = [
            {
                "date": str(row.p_date),
                "avg_score": round(float(row.avg_s), 1),
                "count": row.cnt,
            }
            for row in trend_rows
        ]

        # 4. Phoneme error analysis: examine recent phoneme_results (last 100 practices)
        recent_practices = (
            base_query.filter(self.model.phoneme_results.isnot(None))
            .order_by(desc(self.model.created_at))
            .limit(100)
            .all()
        )

        phoneme_stats = defaultdict(lambda: {"errors": 0, "total": 0})
        for p in recent_practices:
            if not p.phoneme_results:
                continue
            for item in p.phoneme_results:
                ph = item.get("phoneme") or item.get("expected")
                if not ph:
                    continue
                phoneme_stats[ph]["total"] += 1
                status = item.get("status", "").lower()
                score = item.get("score", 100)
                if status != "correct" or score < 60:
                    phoneme_stats[ph]["errors"] += 1

        weak_phonemes = []
        for ph, counts in phoneme_stats.items():
            if counts["errors"] > 0:
                acc_rate = round(
                    ((counts["total"] - counts["errors"]) / counts["total"]) * 100, 1
                )
                weak_phonemes.append(
                    {
                        "phoneme": ph,
                        "error_count": counts["errors"],
                        "total_count": counts["total"],
                        "accuracy_rate": acc_rate,
                    }
                )

        # Sort by most errors, then lowest accuracy rate
        weak_phonemes.sort(key=lambda x: (-x["error_count"], x["accuracy_rate"]))

        return {
            "total_practices": total,
            "average_score": round(float(avg_score), 1),
            "practice_by_type": practice_by_type,
            "weak_phonemes": weak_phonemes[:10],
            "recent_trend": recent_trend,
        }

    def get_student_streak(self, db: Session, student_id: UUID) -> Dict[str, Any]:
        """Tính toán streak luyện tập hàng ngày của học viên."""
        dates_rows = (
            db.query(cast(self.model.created_at, Date).label("p_date"))
            .filter(
                self.model.student_id == student_id,
                self.model.deleted_at.is_(None),
            )
            .distinct()
            .order_by(desc("p_date"))
            .all()
        )

        practice_dates = [row.p_date for row in dates_rows]
        if not practice_dates:
            return {
                "current_streak": 0,
                "longest_streak": 0,
                "last_practice_date": None,
                "today_practiced": False,
                "active_days_this_month": 0,
            }

        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        today_practiced = today in practice_dates
        last_practice_date = practice_dates[0]

        # Calculate current streak
        current_streak = 0
        expected_date = today if today_practiced else yesterday
        for d in practice_dates:
            if d == expected_date:
                current_streak += 1
                expected_date -= timedelta(days=1)
            elif d < expected_date:
                break

        # Calculate longest streak across all history
        longest_streak = 0
        temp_streak = 0
        sorted_dates = sorted(practice_dates)
        prev_d = None
        for d in sorted_dates:
            if prev_d is None:
                temp_streak = 1
            elif (d - prev_d).days == 1:
                temp_streak += 1
            elif (d - prev_d).days > 1:
                temp_streak = 1
            longest_streak = max(longest_streak, temp_streak)
            prev_d = d

        # Active days this current month
        active_days_this_month = sum(
            1 for d in practice_dates if d.year == today.year and d.month == today.month
        )

        return {
            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "last_practice_date": last_practice_date,
            "today_practiced": today_practiced,
            "active_days_this_month": active_days_this_month,
        }


pronunciation_repository = PronunciationRepository()
