import enum
from sqlalchemy import Column, String, Text, Boolean, Integer, ForeignKey, CheckConstraint, UniqueConstraint, Index, func, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PgEnum, TIMESTAMP
from sqlalchemy.orm import relationship
from app.models.base import Base, BaseModel

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

class MemberRole(enum.Enum):
    ADMIN = 'admin'
    MODERATOR = 'moderator'
    MEMBER = 'member'

# ChatRoom Model
class ChatRoom(BaseModel):
    __tablename__ = "chat_rooms"
    
    room_type = Column(Enum(MessageType, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='message_type'), nullable=False)
    title = Column(String(255), nullable=True)
    
    participant1_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    participant2_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=True)
    
    is_active = Column(Boolean, default=True)
    last_message_at = Column(TIMESTAMP(timezone=True), default=func.now())
    
    # Relationships
    messages = relationship("Message", back_populates="chat_room")
    members = relationship("ChatRoomMember", back_populates="chat_room", cascade="all, delete-orphan")
    avatar_url = Column(String(500))  # Group avatar
    description = Column(Text)
    
    __table_args__ = (
        UniqueConstraint('participant1_id', 'participant2_id', name='uq_direct_chat'),
        Index('ix_chat_rooms_participants', 'participant1_id', 'participant2_id'),
    )

# Message Model - UPDATED
class Message(Base):
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=func.gen_random_uuid())
    sender_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    
    chat_room_id = Column(
        UUID(as_uuid=True), 
        ForeignKey('chat_rooms.id', ondelete='CASCADE'),
        nullable=True
    )
    
    message_type = Column(Enum(MessageType, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='message_type'), nullable=False)
    subject = Column(String(255))
    content = Column(Text, nullable=False)
    attachments = Column(JSONB, default=[])
    
    priority = Column(Enum(MessagePriority, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='message_priority'), default=MessagePriority.NORMAL, nullable=False)
    status = Column(Enum(MessageStatus, values_callable=lambda obj: [e.value for e in obj],
        native_enum=False, name='message_status'), default=MessageStatus.SENT, nullable=False)
    
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
    recipient_type = Column(Enum(RecipientType, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='recipient_type'), default=RecipientType.USER, nullable=False)
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

class ChatRoomMember(Base):
    __tablename__ = "chat_room_members"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=func.gen_random_uuid())
    chat_room_id = Column(UUID(as_uuid=True), ForeignKey('chat_rooms.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    role = Column(Enum(MemberRole, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='member_role'), default=MemberRole.MEMBER, nullable=False)
    
    joined_at = Column(TIMESTAMP(timezone=True), default=func.now())
    last_read_at = Column(TIMESTAMP(timezone=True))
    is_muted = Column(Boolean, default=False)
    nickname = Column(String(100))  # Custom nickname in group
    
    # Relationships
    chat_room = relationship("ChatRoom", back_populates="members")
    user = relationship("User", backref="group_memberships")
    
    __table_args__ = (
        UniqueConstraint('chat_room_id', 'user_id', name='uq_room_member'),
        Index('ix_room_members_user', 'user_id'),
        Index('ix_room_members_room', 'chat_room_id'),
    )