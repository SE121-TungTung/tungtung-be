# app/schemas/notification.py
from pydantic import BaseModel
from typing import Optional, Any, List, Dict
from datetime import datetime
from uuid import UUID
from app.models.notification import NotificationType, NotificationPriority

class NotificationBase(BaseModel):
    title: str
    content: str
    notification_type: NotificationType
    priority: NotificationPriority = NotificationPriority.NORMAL
    data: Optional[Dict[str, Any]] = {}
    action_url: Optional[str] = None
    channels: List[str] = ["in_app"]

class NotificationCreate(NotificationBase):
    user_id: UUID
    expires_at: Optional[datetime] = None

class NotificationUpdate(BaseModel):
    read_at: Optional[datetime] = None
    dismissed_at: Optional[datetime] = None

class NotificationResponse(NotificationBase):
    id: UUID
    user_id: UUID
    read_at: Optional[datetime]
    created_at: datetime
    sent_channels: Optional[Dict[str, Any]]

    model_config = {
        "from_attributes": True
    }

class NotificationListResponse(BaseModel):
    notifications: List[NotificationResponse]
    total: int

class BroadcastNotificationCreate(BaseModel):
    target_type: str  # "all", "role", "specific_users"
    target_role: Optional[str] = None  # "student", "teacher", "admin", "center_admin"
    target_user_ids: Optional[List[UUID]] = None
    title: str
    content: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    action_url: Optional[str] = None
    channels: List[str] = ["in_app"]