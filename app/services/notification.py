from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import BackgroundTasks
from uuid import UUID

from app.repositories.notification import notification_repo
from app.schemas.notification import NotificationCreate
from app.services.websocket import manager as websocket_manager


class NotificationService:
    async def send_notification(
        self,
        db: Session,
        noti_info: NotificationCreate,
        background_tasks: BackgroundTasks | None = None,
    ):
        # 1. Lưu notification vào DB (commit trong service – giữ nguyên)
        notification = notification_repo.create(db, obj_in=noti_info)

        # 2. Realtime WebSocket – chỉ xử lý kênh in_app
        if "in_app" in notification.channels:
            payload = {
                "type": "NEW_NOTIFICATION",
                "data": {
                    "id": str(notification.id),
                    "title": notification.title,
                    "content": notification.content,
                    "priority": notification.priority,
                    "action_url": notification.action_url,
                },
            }

            await websocket_manager.send_to_user(
                notification.user_id,
                payload,
            )

        return notification

    def mark_as_read(
        self,
        db: Session,
        notification_id: str,
        user_id: str,
    ):
        noti = notification_repo.get(db, id=notification_id)
        if not noti or str(noti.user_id) != str(user_id):
            return None

        if not noti.read_at:
            noti.read_at = datetime.now()
            db.commit()
            db.refresh(noti)

        return noti

    async def mark_all_as_read(
        self,
        db: Session,
        user_id: UUID,
    ) -> dict:
        
        updated_count = notification_repo.mark_all_as_read(db, user_id)

        return {
            "success": True,
            "message": f"Marked {updated_count} notifications as read",
            "updated_count": updated_count,
        }


notification_service = NotificationService()
