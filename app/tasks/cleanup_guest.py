"""
Celery task: xóa tài khoản Guest đã hết hạn (>30 ngày).
Chạy theo lịch beat: mỗi ngày 3:00 AM UTC.

Logic:
- Query users WHERE role='guest' AND deleted_at IS NULL
- Kiểm tra preferences->>'guest_expires_at' < now()
- Soft-delete (set deleted_at = now())
"""
from datetime import datetime, timezone
from celery.utils.log import get_task_logger

from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.user import User, UserRole

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.cleanup_guest.cleanup_expired_guests", bind=True, max_retries=3)
def cleanup_expired_guests(self):
    """Soft-delete Guest accounts whose guest_expires_at has passed."""
    db = SessionLocal()
    deleted_count = 0
    try:
        now = datetime.now(timezone.utc)

        guests = (
            db.query(User)
            .filter(
                User.role == UserRole.GUEST,
                User.deleted_at.is_(None),
            )
            .all()
        )

        for user in guests:
            prefs = user.preferences or {}
            expires_str = prefs.get("guest_expires_at")
            if not expires_str:
                # Không có expires_at → xem như đã hết hạn ngay
                user.deleted_at = now
                deleted_count += 1
                continue

            try:
                # ISO format, có thể không có timezone info
                expires_at = datetime.fromisoformat(expires_str)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            except ValueError:
                logger.warning("Invalid guest_expires_at for user %s: %s", user.id, expires_str)
                continue

            if expires_at <= now:
                user.deleted_at = now
                deleted_count += 1

        db.commit()
        logger.info("Cleanup guest task: soft-deleted %d expired guest accounts.", deleted_count)
        return {"deleted": deleted_count}

    except Exception as exc:
        db.rollback()
        logger.error("Cleanup guest task failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 10)  # retry sau 10 phút
    finally:
        db.close()
