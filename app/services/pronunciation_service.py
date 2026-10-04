import io
import math
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
from datetime import datetime, date, timedelta
import httpx
from sqlalchemy.orm import Session
import cloudinary.uploader

from app.core.config import settings
from app.core.exceptions import APIException, AIServiceException
from app.core.rate_limit import RateLimiter
from app.models.user import User, UserRole
from app.models.pronunciation import PronunciationPractice, TargetType
from app.repositories.pronunciation import pronunciation_repository

from app.repositories.phoneme_mastery import phoneme_mastery_repository, assessment_repository

logger = logging.getLogger(__name__)

# Reusable Rate Limiter for pronunciation practice
pronunciation_rate_limiter = RateLimiter(
    resource="pronunciation_practice",
    role_limits={
        UserRole.GUEST_STUDENT: 10,
        UserRole.STUDENT: 50,
        UserRole.TEACHER: 100,
        UserRole.TA: 100,
        UserRole.CENTER_ADMIN: 500,
        UserRole.SYSTEM_ADMIN: 500,
    },
    default_limit=50,
    period_seconds=86400,
)


class PronunciationService:
    def __init__(self):
        self.repository = pronunciation_repository
        self.mastery_repository = phoneme_mastery_repository
        self.rate_limiter = pronunciation_rate_limiter

    async def grade_and_save_practice(
        self,
        db: Session,
        student: User,
        audio_filename: str,
        audio_bytes: bytes,
        audio_content_type: str,
        target: str,
        target_type: TargetType,
        accent: str = "US",
    ) -> PronunciationPractice:
        """
        Gửi file audio sang AI Service để chấm điểm phát âm 7 thành phần,
        upload audio lưu trữ, và lưu kết quả vào database.
        Sau đó tự động cập nhật phoneme mastery (SM-2 spaced repetition).
        """
        # 1. Check and consume rate limit
        await self.rate_limiter.check_and_consume(student.id, student.role)

        # 2. Call AI Service
        ai_url = f"{settings.AI_BASE_URL.rstrip('/')}/grade/pronunciation/practice"
        target_type_str = target_type.value if hasattr(target_type, "value") else str(target_type)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                files = {
                    "audio": (
                        audio_filename or "practice.wav",
                        audio_bytes,
                        audio_content_type or "audio/wav",
                    )
                }
                form_data = {
                    "target": target,
                    "target_type": target_type_str,
                    "accent": accent,
                }
                response = await client.post(ai_url, data=form_data, files=files)

                if response.status_code != 200:
                    logger.error(
                        f"AI Service error [{response.status_code}]: {response.text}"
                    )
                    await self.rate_limiter.rollback(student.id)
                    raise AIServiceException(
                        message="Dịch vụ chấm điểm AI gặp lỗi khi xử lý bài phát âm.",
                        details=response.text,
                    )

                ai_result = response.json()

        except httpx.RequestError as exc:
            logger.error(f"Cannot reach AI Service at {ai_url}: {exc}")
            await self.rate_limiter.rollback(student.id)
            raise AIServiceException(
                message="Không thể kết nối đến AI Service chấm phát âm. Vui lòng thử lại sau.",
                details=str(exc),
            )
        except Exception as exc:
            if not isinstance(exc, APIException):
                await self.rate_limiter.rollback(student.id)
            raise

        # 3. Upload audio to Cloudinary (optional fallback if fails)
        audio_url = None
        try:
            if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY:
                upload_res = cloudinary.uploader.upload(
                    audio_bytes,
                    resource_type="auto",
                    folder="pronunciation_audio",
                    public_id=f"pronunciation_{student.id}_{int(datetime.utcnow().timestamp())}",
                )
                audio_url = upload_res.get("secure_url")
        except Exception as e:
            logger.warning(f"Cloudinary upload failed for pronunciation practice: {e}")

        # 4. Extract fields from AI response
        overall_score = float(ai_result.get("overall_score", 0.0))
        target_ipa = ai_result.get("target_ipa")
        actual_ipa = ai_result.get("actual_ipa")
        component_scores = ai_result.get("component_scores")
        phoneme_results = ai_result.get("phoneme_results")
        error_summary = ai_result.get("error_summary")
        feedback_text = ai_result.get("feedback_text")
        processing_time_ms = ai_result.get("processing_time_ms")

        # 5. Persist practice to DB
        practice_data = {
            "student_id": student.id,
            "target_text": target,
            "target_type": target_type,
            "target_ipa": target_ipa,
            "actual_ipa": actual_ipa,
            "overall_score": overall_score,
            "phoneme_results": phoneme_results,
            "component_scores": component_scores,
            "error_summary": error_summary,
            "feedback_text": feedback_text,
            "processing_time_ms": processing_time_ms,
            "audio_url": audio_url,
            "created_by": student.id,
        }

        practice = self.repository.create_practice(db, practice_data)

        # 6. Update phoneme mastery (SM-2 Spaced Repetition)
        if phoneme_results:
            try:
                self.mastery_repository.batch_update_from_phoneme_results(
                    db=db,
                    student_id=student.id,
                    phoneme_results=phoneme_results,
                )
            except Exception as e:
                logger.warning(f"Phoneme mastery update failed (non-critical): {e}")

        return practice

    def get_practice_detail(
        self, db: Session, practice_id: UUID, current_user: User
    ) -> PronunciationPractice:
        """Lấy chi tiết 1 bài phát âm kèm kiểm tra quyền."""
        practice = self.repository.get_by_id(db, practice_id)
        if not practice:
            raise APIException(
                status_code=404,
                code="PRACTICE_NOT_FOUND",
                message="Không tìm thấy lượt luyện phát âm.",
            )

        # Học viên chỉ được xem bài của mình, giáo viên và admin được xem bài của học viên
        privileged_roles = [
            UserRole.TEACHER,
            UserRole.TA,
            UserRole.CENTER_ADMIN,
            UserRole.SYSTEM_ADMIN,
        ]
        if current_user.role not in privileged_roles and practice.student_id != current_user.id:
            raise APIException(
                status_code=403,
                code="AUTH_PERMISSION_DENIED",
                message="Bạn không có quyền xem kết quả luyện tập này.",
            )

        return practice

    def get_student_history(
        self,
        db: Session,
        student_id: UUID,
        target_type: Optional[TargetType] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Lấy danh sách lịch sử luyện tập phát âm có phân trang."""
        if page < 1:
            page = 1
        if limit < 1:
            limit = 20
        skip = (page - 1) * limit

        items, total = self.repository.get_student_practices(
            db=db,
            student_id=student_id,
            target_type=target_type,
            skip=skip,
            limit=limit,
        )

        total_pages = math.ceil(total / limit) if total > 0 else 0
        return {
            "items": items,
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
            },
        }

    def get_student_stats(self, db: Session, student_id: UUID) -> Dict[str, Any]:
        """Lấy tổng hợp thống kê phát âm của học viên."""
        return self.repository.get_student_stats(db, student_id)

    def get_student_streak(self, db: Session, student_id: UUID) -> Dict[str, Any]:
        """Lấy thông tin chuỗi ngày luyện tập của học viên."""
        return self.repository.get_student_streak(db, student_id)

    # ── Phoneme Mastery endpoints ──────────────────────────────

    def get_phoneme_mastery_summary(
        self, db: Session, student_id: UUID
    ) -> Dict[str, Any]:
        """Tổng hợp mastery (cho Radar Chart + Dashboard)."""
        return self.mastery_repository.get_mastery_summary(db, student_id)

    def get_due_for_review(
        self, db: Session, student_id: UUID, limit: int = 10
    ) -> List:
        """Lấy danh sách phonemes cần ôn lại theo SR schedule."""
        items = self.mastery_repository.get_due_for_review(db, student_id, limit)
        return [
            {
                "phoneme": m.phoneme,
                "mastery_level": m.mastery_level,
                "last_score": float(m.last_score) if m.last_score else None,
                "interval_days": m.interval_days,
                "next_review_at": str(m.next_review_at) if m.next_review_at else None,
            }
            for m in items
        ]

    def get_phoneme_mastery_map(
        self, db: Session, student_id: UUID
    ) -> List[Dict[str, Any]]:
        """Bản đồ 44 phoneme IPA với mã màu mastery cho FE."""
        all_mastery = self.mastery_repository.get_student_mastery_all(db, student_id)
        mastery_map = {m.phoneme: m for m in all_mastery}

        ALL_44_PHONEMES = [
            # Consonants
            "p", "b", "t", "d", "k", "g", "ʔ",
            "f", "v", "θ", "ð", "s", "z", "ʃ", "ʒ", "h",
            "tʃ", "dʒ",
            "m", "n", "ŋ",
            "l", "r", "j", "w",
            # Vowels
            "iː", "ɪ", "eɪ", "ɛ", "æ",
            "ɑː", "ɒ", "ɔː", "ɔɪ",
            "oʊ", "ʊ", "uː",
            "aɪ", "aʊ",
            "ə", "ɜː", "ʌ",
            "ɪə", "eə", "ʊə",
        ]

        result = []
        for ph in ALL_44_PHONEMES:
            m = mastery_map.get(ph)
            if m:
                result.append({
                    "phoneme": ph,
                    "mastery_level": m.mastery_level,
                    "avg_score": float(m.avg_score_7d) if m.avg_score_7d else None,
                    "total_attempts": m.total_attempts,
                    "status": ["unseen", "learning", "familiar", "practiced", "mastered"][m.mastery_level],
                })
            else:
                result.append({
                    "phoneme": ph,
                    "mastery_level": 0,
                    "avg_score": None,
                    "total_attempts": 0,
                    "status": "unseen",
                })

        return result

    # ── Assessment (Placement Test) ─────────────────────────────

    # Mapping sample words cho placement test — 10 từ bao phủ 8 nhóm âm
    ASSESSMENT_WORD_POOL = [
        {"text": "think", "type": "word", "ipa": "/θɪŋk/", "phonemes": ["θ", "ɪ", "ŋ", "k"]},
        {"text": "breathe", "type": "word", "ipa": "/briːð/", "phonemes": ["b", "r", "iː", "ð"]},
        {"text": "comfortable", "type": "word", "ipa": "/ˈkʌmftəbl/", "phonemes": ["k", "ʌ", "m", "f", "t", "ə", "b", "l"]},
        {"text": "vegetable", "type": "word", "ipa": "/ˈvedʒtəbl/", "phonemes": ["v", "ɛ", "dʒ", "t", "ə", "b", "l"]},
        {"text": "photograph", "type": "word", "ipa": "/ˈfoʊtəɡræf/", "phonemes": ["f", "oʊ", "t", "ə", "g", "r", "æ", "f"]},
        {"text": "architecture", "type": "word", "ipa": "/ˈɑːrkɪtektʃər/", "phonemes": ["ɑː", "k", "ɪ", "t", "ɛ", "k", "tʃ", "ə"]},
        {"text": "schedule", "type": "word", "ipa": "/ˈskedʒuːl/", "phonemes": ["ʃ", "ɛ", "dʒ", "uː", "l"]},
        {"text": "enthusiasm", "type": "word", "ipa": "/ɪnˈθuːziæzəm/", "phonemes": ["ɪ", "n", "θ", "uː", "z", "i", "æ", "z", "ə", "m"]},
        {"text": "The weather throughout the year varies significantly.", "type": "sentence", "ipa": "/ðə ˈweðər θruːˈaʊt ðə jɪr ˈveriz sɪɡˈnɪfɪkəntli/", "phonemes": ["ð", "ə", "w", "ɛ", "ð", "ə", "θ", "r", "uː", "aʊ", "t"]},
        {"text": "She sells seashells by the seashore.", "type": "sentence", "ipa": "/ʃiː sɛlz ˈsiːʃɛlz baɪ ðə ˈsiːʃɔːr/", "phonemes": ["ʃ", "iː", "s", "ɛ", "l", "z", "ʃ", "ɔː"]},
    ]

    def get_assessment_items(self) -> List[Dict[str, Any]]:
        """Trả về danh sách 10 items cho placement test có phiên âm IPA chuẩn."""
        return [
            {
                "target_text": item["text"],
                "target_type": item["type"],
                "ipa": item.get("ipa", ""),
                "phonemes": item.get("phonemes", []),
            }
            for item in self.ASSESSMENT_WORD_POOL
        ]

    def submit_assessment(
        self,
        db: Session,
        student_id: UUID,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Xử lý kết quả placement test:
        1. Phân tích phoneme errors across all items
        2. Ước lượng CEFR level + IELTS band
        3. Xác định weak/strong phonemes
        4. Lưu vào DB
        """
        # Collect phoneme scores across all items
        phoneme_scores: Dict[str, List[float]] = {}
        for item in items:
            if not item.get("phoneme_results"):
                continue
            for pr in item["phoneme_results"]:
                ph = pr.get("phoneme_expected") or pr.get("phoneme")
                if not ph:
                    continue
                score = pr.get("confidence", 0.5) * 100 if pr.get("is_correct") else pr.get("confidence", 0.0) * 30
                phoneme_scores.setdefault(ph, []).append(score)

        # Calculate per-phoneme averages
        phoneme_avgs = {
            ph: sum(scores) / len(scores)
            for ph, scores in phoneme_scores.items()
        }

        # Identify weak (<60%) and strong (>=80%) phonemes
        weak = sorted([ph for ph, avg in phoneme_avgs.items() if avg < 60], key=lambda p: phoneme_avgs[p])
        strong = [ph for ph, avg in phoneme_avgs.items() if avg >= 80]

        # Overall average score
        all_scores = [item.get("overall_score", 0) for item in items]
        avg_overall = sum(all_scores) / len(all_scores) if all_scores else 0

        # Estimate CEFR + IELTS band
        if avg_overall >= 85:
            cefr, ielts = "C1", 7.5
        elif avg_overall >= 72:
            cefr, ielts = "B2", 6.5
        elif avg_overall >= 58:
            cefr, ielts = "B1", 5.5
        elif avg_overall >= 40:
            cefr, ielts = "A2", 4.5
        else:
            cefr, ielts = "A1", 3.5

        # Check retake count
        latest = assessment_repository.get_latest(db, student_id)
        retake = (latest.retake_count + 1) if latest else 0

        # Save to DB
        assessment_data = {
            "student_id": student_id,
            "cefr_level": cefr,
            "ielts_band_estimate": ielts,
            "weak_phonemes": weak[:15],
            "strong_phonemes": strong[:15],
            "assessment_items": items,
            "retake_count": retake,
            "created_by": student_id,
        }
        assessment = assessment_repository.create_assessment(db, assessment_data)

        # Seed mastery records for weak phonemes
        for ph in weak:
            self.mastery_repository.get_or_create(db, student_id, ph)
        db.commit()

        return {
            "id": assessment.id,
            "cefr_level": cefr,
            "ielts_band_estimate": ielts,
            "weak_phonemes": weak[:15],
            "strong_phonemes": strong[:15],
            "assessment_items": items,
            "retake_count": retake,
            "created_at": assessment.created_at,
        }

    def get_latest_assessment(
        self, db: Session, student_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """Lấy kết quả placement test gần nhất."""
        a = assessment_repository.get_latest(db, student_id)
        if not a:
            return None
        return {
            "id": a.id,
            "cefr_level": a.cefr_level,
            "ielts_band_estimate": float(a.ielts_band_estimate) if a.ielts_band_estimate else None,
            "weak_phonemes": a.weak_phonemes or [],
            "strong_phonemes": a.strong_phonemes or [],
            "retake_count": a.retake_count,
            "created_at": a.created_at,
        }

    # ── Daily Missions ──────────────────────────────────────────

    # Example word bank per phoneme for mission generation
    PHONEME_WORD_BANK: Dict[str, List[str]] = {
        "θ": ["think", "thought", "through", "therapy", "thunder"],
        "ð": ["the", "this", "that", "breathe", "mother"],
        "ʃ": ["she", "ship", "nation", "official", "pressure"],
        "ʒ": ["vision", "measure", "pleasure", "decision", "genre"],
        "tʃ": ["church", "chapter", "achieve", "champion", "nature"],
        "dʒ": ["judge", "giant", "gesture", "gentle", "journey"],
        "ŋ": ["sing", "ring", "thinking", "among", "tongue"],
        "æ": ["cat", "bat", "apple", "travel", "champion"],
        "ʌ": ["cup", "but", "love", "mother", "struggle"],
        "ə": ["about", "above", "banana", "chocolate", "comfortable"],
        "ɜː": ["bird", "word", "nurse", "earth", "learn"],
        "ɪ": ["sit", "bit", "fish", "listen", "system"],
        "iː": ["see", "eat", "team", "receive", "achieve"],
        "ʊ": ["put", "book", "good", "should", "woman"],
        "uː": ["too", "blue", "food", "school", "through"],
    }

    SENTENCE_DRILLS = [
        "The quick brown fox jumps over the lazy dog.",
        "She sells seashells by the seashore.",
        "Peter Piper picked a peck of pickled peppers.",
        "Technology has significantly transformed modern education.",
        "Environmental sustainability requires collective global action.",
    ]

    def get_daily_missions(
        self, db: Session, student_id: UUID
    ) -> Dict[str, Any]:
        """
        Tạo 5-8 nhiệm vụ luyện tập cá nhân hóa cho ngày hôm nay.
        Ưu tiên:
            1. SR Review (phonemes đến hạn ôn)
            2. Weak Practice (âm yếu từ assessment)
            3. New Phoneme (khám phá âm chưa luyện)
            4. Sentence Drill (luyện câu hoàn chỉnh)
        """
        import random
        today = datetime.utcnow().date()
        missions: List[Dict[str, Any]] = []

        # 1. SR Review missions (max 3)
        due_phonemes = self.mastery_repository.get_due_for_review(db, student_id, limit=3)
        for i, m in enumerate(due_phonemes):
            words = self.PHONEME_WORD_BANK.get(m.phoneme, [m.phoneme])
            word = random.choice(words) if words else m.phoneme
            missions.append({
                "mission_id": f"sr_{today}_{m.phoneme}",
                "type": "review",
                "label": f"Ôn tập: /{m.phoneme}/",
                "description": f"Âm /{m.phoneme}/ cần ôn lại (interval: {m.interval_days} ngày)",
                "target_text": word,
                "target_type": "word",
                "phoneme": m.phoneme,
                "priority": 10 - i,
                "completed": False,
            })

        # 2. Weak phoneme practice (max 2)
        assessment = assessment_repository.get_latest(db, student_id)
        if assessment and assessment.weak_phonemes:
            weak_list = assessment.weak_phonemes[:5]
            random.shuffle(weak_list)
            for ph in weak_list[:2]:
                if any(m["phoneme"] == ph for m in missions):
                    continue  # skip if already in SR
                words = self.PHONEME_WORD_BANK.get(ph, [ph])
                word = random.choice(words) if words else ph
                missions.append({
                    "mission_id": f"weak_{today}_{ph}",
                    "type": "weak_practice",
                    "label": f"Luyện âm yếu: /{ph}/",
                    "description": f"Âm /{ph}/ được đánh giá là cần cải thiện",
                    "target_text": word,
                    "target_type": "word",
                    "phoneme": ph,
                    "priority": 5,
                    "completed": False,
                })

        # 3. New phoneme discovery (1 mission)
        all_mastery = self.mastery_repository.get_student_mastery_all(db, student_id)
        practiced_phonemes = {m.phoneme for m in all_mastery}
        all_phonemes = set(self.PHONEME_WORD_BANK.keys())
        new_phonemes = list(all_phonemes - practiced_phonemes)
        if new_phonemes:
            ph = random.choice(new_phonemes)
            words = self.PHONEME_WORD_BANK.get(ph, [ph])
            missions.append({
                "mission_id": f"new_{today}_{ph}",
                "type": "new_phoneme",
                "label": f"Khám phá âm mới: /{ph}/",
                "description": f"Thử luyện âm /{ph}/ lần đầu tiên!",
                "target_text": random.choice(words) if words else ph,
                "target_type": "word",
                "phoneme": ph,
                "priority": 3,
                "completed": False,
            })

        # 4. Sentence drill (1 mission)
        sentence = random.choice(self.SENTENCE_DRILLS)
        missions.append({
            "mission_id": f"sentence_{today}",
            "type": "sentence",
            "label": "Luyện câu hoàn chỉnh",
            "description": "Luyện phát âm câu dài để cải thiện fluency và linking",
            "target_text": sentence,
            "target_type": "sentence",
            "phoneme": None,
            "priority": 1,
            "completed": False,
        })

        # Sort by priority descending
        missions.sort(key=lambda x: -x["priority"])

        # Check today's streak
        streak = self.repository.get_student_streak(db, student_id)
        streak_bonus = streak.get("current_streak", 0) >= 3

        return {
            "date": str(today),
            "missions": missions,
            "total_missions": len(missions),
            "completed_count": 0,  # TODO: track from DB
            "streak_bonus": streak_bonus,
        }


pronunciation_service = PronunciationService()
