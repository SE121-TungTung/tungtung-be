# app/services/notification_service.py
from sqlalchemy.orm import Session
from datetime import datetime
from app.repositories.notification import notification_repo
from app.schemas.notification import NotificationCreate
from app.services.websocket import manager as websocket_manager # Import websocket manager hiện có
from app.services.email import email_service # Giả định function gửi mail có sẵn
from fastapi import BackgroundTasks
from uuid import UUID

class NotificationService:
    async def send_notification(
        self, 
        db: Session, 
        noti_info: NotificationCreate, 
        background_tasks: BackgroundTasks = None
    ):
        # 1. Lưu vào Database
        notification = notification_repo.create(db, obj_in=noti_info)
        
        # 2. Xử lý gửi Realtime (WebSocket) - Kênh "in_app"
        if "in_app" in notification.channels:
            payload = {
                "type": "NEW_NOTIFICATION",
                "data": {
                    "id": str(notification.id),
                    "title": notification.title,
                    "content": notification.content,
                    "priority": notification.priority,
                    "action_url": notification.action_url
                }
            }
            # Gọi hàm gửi tin nhắn cá nhân trong websocket manager của bạn
            await websocket_manager.send_personal_message(
                str(notification.user_id), 
                payload
            )

        # 3. Xử lý gửi Email (Async/Background) - Kênh "email"
        if "email" in notification.channels and background_tasks:
            from app.repositories.user import user_repo
            user = user_repo.get(db, id=notification.user_id)
            if user and user.email:
                background_tasks.add_task(
                    self._send_email_notification, 
                    user.email, 
                    notification.title, 
                    notification.content
                )
                
                # Cập nhật sent_channels (Optional - cần logic phức tạp hơn để confirm sent)
                notification.sent_channels["email"] = datetime.now().isoformat()
                db.commit()

        return notification

    async def _send_email_notification(self, email: str, subject: str, body: str):
        print(f"Sending email to {email}: {subject}")
        # await email_service.send_welcome_email(email, subject, body) 
        pass

    def mark_as_read(self, db: Session, notification_id: str, user_id: str):
        noti = notification_repo.get(db, id=notification_id)
        if not noti or str(noti.user_id) != str(user_id):
            return None
        
        if not noti.read_at:
            noti.read_at = datetime.now()
            db.commit()
            db.refresh(noti)
        return noti
    
    async def mark_all_as_read(self, db: Session, user_id: UUID) -> dict:
        """Service mark all notifications as read"""
        updated_count = self.notification_repo.mark_all_as_read(db, user_id)
        return {
            "success": True, 
            "message": f"Marked {updated_count} notifications as read",
            "updated_count": updated_count
        }

notification_service = NotificationService()