# app/models/notification.py
import uuid
from sqlalchemy import Column, String, Text, ForeignKey, DateTime, func, Enum
import enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import Base

class NotificationType(enum.Enum):
    SCHEDULE_CHANGE = "schedule_change"         
    ASSIGNMENT_DUE = "assignment_due"           
    GRADE_AVAILABLE = "grade_available"         
    ATTENDANCE_REMINDER = "attendance_reminder"
    CLASS_ANNOUNCEMENT = "class_announcement"
    
    MESSAGE_RECEIVED = "message_received"
    ACHIEVEMENT = "achievement"
  
    PAYMENT_DUE = "payment_due"                 
    SYSTEM_ALERT = "system_alert"
    MAINTENANCE_NOTICE = "maintenance_notice"

class NotificationPriority(enum.Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    
    notification_type = Column(Enum(NotificationType, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='notification_type'), nullable=False)
    priority = Column(Enum(NotificationPriority, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='notification_priority'), default=NotificationPriority.NORMAL, nullable=False)
    
    data = Column(JSONB, default=dict)  # Metadata bổ sung
    action_url = Column(Text, nullable=True)  # Link để redirect khi user click
    
    read_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Định nghĩa các kênh gửi: ["in_app", "email", "push"]
    channels = Column(JSONB, default=lambda: ["in_app"]) 
    # Log trạng thái gửi: {"email": "2023...", "push": "failed"}
    sent_channels = Column(JSONB, default=dict)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    user = relationship("User", backref="notifications")