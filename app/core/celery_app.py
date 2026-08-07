from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "tungtung_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.ga_tasks",
        "app.tasks.cleanup_guest",  # Guest cleanup cron
    ]
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # Chạy mỗi ngày lúc 3:00 AM UTC
        "cleanup-expired-guests-daily": {
            "task": "app.tasks.cleanup_guest.cleanup_expired_guests",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)
