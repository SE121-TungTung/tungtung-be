import enum
from sqlalchemy import Column, String, Text, Boolean, Integer, ForeignKey, CheckConstraint, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PgEnum, TIMESTAMP
from sqlalchemy.orm import relationship
from app.models.base import Base

# Enums (giữ nguyên)
class MessageType(enum.Enum):
    DIRECT = 'direct'
    GROUP = 'group'
    CLASS = 'class'
    SYSTEM = 'system'
    ANNOUNCEMENT = 'announcement'

class MessagePriority(enum.Enum):
    LOW = 'low'
    NORMAL = 'normal'
    HIGH = 'high'
    URGENT = 'urgent'

class MessageStatus(enum.Enum):
    DRAFT = 'draft'
    SCHEDULED = 'scheduled'
    SENT = 'sent'
    DELIVERED = 'delivered'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

class RecipientType(enum.Enum):
    USER = 'user'
    GROUP = 'group'
    CLASS = 'class'

# ChatRoom Model
class ChatRoom(Base):
    __tablename__ = "chat_rooms"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=func.gen_random_uuid())
    room_type = Column(PgEnum(MessageType, name='message_type', create_type=False), nullable=False)
    title = Column(String(255), nullable=True)
    
    participant1_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    participant2_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
    is_active = Column(Boolean, default=True)
    last_message_at = Column(TIMESTAMP(timezone=True), default=func.now())
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    
    # Relationships
    messages = relationship("Message", back_populates="chat_room")
    
    __table_args__ = (
        UniqueConstraint('participant1_id', 'participant2_id', name='uq_direct_chat'),
        Index('ix_chat_rooms_participants', 'participant1_id', 'participant2_id'),
    )

# Message Model - UPDATED
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=func.gen_random_uuid())
    sender_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    chat_room_id = Column(
        UUID(as_uuid=True), 
        ForeignKey('chat_rooms.id', ondelete='CASCADE'),
        nullable=True
    )
    
    message_type = Column(PgEnum(MessageType, name='message_type', create_type=False), nullable=False)
    subject = Column(String(255))
    content = Column(Text, nullable=False)
    attachments = Column(JSONB, default=[])
    
    priority = Column(PgEnum(MessagePriority, name='message_priority', create_type=False), default=MessagePriority.NORMAL)
    status = Column(PgEnum(MessageStatus, name='message_status', create_type=False), default=MessageStatus.SENT)
    
    scheduled_at = Column(TIMESTAMP(timezone=True))
    expires_at = Column(TIMESTAMP(timezone=True))
    
    ai_moderated = Column(Boolean, default=False)
    ai_warning = Column(Text)
    read_receipt_requested = Column(Boolean, default=False)
    
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())
    
    # Relationships
    sender = relationship("User", foreign_keys=[sender_id], backref="sent_messages")
    chat_room = relationship("ChatRoom", back_populates="messages")  # ✅ THÊM
    recipients = relationship("MessageRecipient", back_populates="message", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('ix_messages_chat_room_created', 'chat_room_id', 'created_at'),
        Index('ix_messages_sender_created', 'sender_id', 'created_at'),
    )

# MessageRecipient - UPDATED
class MessageRecipient(Base):
    __tablename__ = "message_recipients"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=func.gen_random_uuid())
    message_id = Column(UUID(as_uuid=True), ForeignKey('messages.id', ondelete='CASCADE'), nullable=False)
    recipient_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    recipient_type = Column(PgEnum(RecipientType, name='recipient_type', create_type=False), default=RecipientType.USER)
    
    read_at = Column(TIMESTAMP(timezone=True))
    replied_at = Column(TIMESTAMP(timezone=True))
    archived = Column(Boolean, default=False)
    starred = Column(Boolean, default=False)
    deleted = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    
    message = relationship("Message", back_populates="recipients")
    recipient = relationship("User", foreign_keys=[recipient_id], backref="received_messages")
    
    __table_args__ = (
        UniqueConstraint('message_id', 'recipient_id', name='uq_msg_recipient'),
        Index('ix_msg_recipient_unread', 'recipient_id', 'read_at'),
        Index('ix_msg_recipient_user', 'recipient_id', 'deleted'),
    )