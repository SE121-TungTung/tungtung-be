import io
import math
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
import httpx
from sqlalchemy.orm import Session
import cloudinary.uploader

from app.core.config import settings
from app.core.exceptions import APIException, AIServiceException
from app.core.rate_limit import RateLimiter
from app.models.user import User, UserRole
from app.models.pronunciation import PronunciationPractice, TargetType
from app.repositories.pronunciation import pronunciation_repository

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
    ) -> PronunciationPractice:
        """
        Gửi file audio sang AI Service để chấm điểm phát âm 7 thành phần,
        upload audio lưu trữ, và lưu kết quả vào database.
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

        # 5. Persist to DB
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


pronunciation_service = PronunciationService()
