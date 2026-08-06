from sqlalchemy.orm import Session
from datetime import datetime
from uuid import UUID
from typing import List, Optional


from app.repositories.notification import notification_repo
from app.schemas.notification import NotificationCreate
from app.services.websocket import websocket_manager

import asyncio

class NotificationService:
    async def send_notification(
        self,
        db: Session,
        noti_info: NotificationCreate,
    ):
        # 1. Lưu notification vào DB (commit trong service – giữ nguyên)
        notification = notification_repo.create(db, obj_in=noti_info.dict())

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
        db.commit()
        return {
            "success": True,
            "message": f"Marked {updated_count} notifications as read",
            "updated_count": updated_count,
        }

    def send_notification_sync(self, db: Session, noti_info: NotificationCreate):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Đang ở trong event loop (FastAPI)
            return asyncio.create_task(
                self.send_notification(db, noti_info)
            )
        else:
            # Chạy sync context
            asyncio.run(
                self.send_notification(db, noti_info)
            )

    async def broadcast_notification(
        self,
        db: Session,
        user_ids: List[UUID],
        title: str,
        content: str,
        priority: str = "normal",
        action_url: Optional[str] = None,
        channels: List[str] = ["in_app"],
        notification_type: Optional[str] = None
    ):
        from app.models.notification import Notification, NotificationType, NotificationPriority
        
        # Determine notification type enum
        noti_type_enum = NotificationType.SYSTEM_ALERT
        if notification_type:
            if isinstance(notification_type, str):
                try:
                    noti_type_enum = NotificationType(notification_type)
                except ValueError:
                    noti_type_enum = NotificationType.SYSTEM_ALERT
            else:
                noti_type_enum = notification_type

        # 1. Bulk insert to DB
        notifications = []
        for u_id in user_ids:
            noti = Notification(
                user_id=u_id,
                title=title,
                content=content,
                notification_type=noti_type_enum,
                priority=NotificationPriority(priority) if isinstance(priority, str) else priority,
                action_url=action_url,
                channels=channels
            )
            notifications.append(noti)
        
        db.add_all(notifications)
        db.commit()
        
        # 2. WebSocket broadcast
        if "in_app" in channels:
            for noti in notifications:
                payload = {
                    "type": "NEW_NOTIFICATION",
                    "data": {
                        "id": str(noti.id),
                        "title": noti.title,
                        "content": noti.content,
                        "priority": noti.priority.value if hasattr(noti.priority, 'value') else noti.priority,
                        "action_url": noti.action_url,
                    },
                }
                await websocket_manager.send_to_user(noti.user_id, payload)
        
        return len(notifications)

notification_service = NotificationService()

async def run_broadcast_task(
    user_ids: List[UUID],
    title: str,
    content: str,
    priority: str,
    action_url: Optional[str],
    channels: List[str],
    notification_type: Optional[str] = None
):
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        await notification_service.broadcast_notification(
            db=db,
            user_ids=user_ids,
            title=title,
            content=content,
            priority=priority,
            action_url=action_url,
            channels=channels,
            notification_type=notification_type
        )
    finally:
        db.close()

