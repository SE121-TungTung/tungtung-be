from uuid import UUID
from typing import Optional, Any
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone
from fastapi import HTTPException

# Import Models & Schemas
from app.core.exceptions import APIException
from app.models.message import Message, ChatRoom, ChatRoomMember, MessageType, MessageStatus
from app.models.user import User
from app.models.notification import NotificationType, NotificationPriority
from app.schemas.message import MessageCreate, MessageResponse
from app.schemas.notification import NotificationCreate

from app.repositories.message import (
    message_repository, 
    recipient_repository, 
    chat_room_repository
)

class MessageSenderService:
    def __init__(self):
        self.message_repo = message_repository
        self.recipient_repo = recipient_repository
        self.chat_room_repo = chat_room_repository

    async def handle_new_message(
        self, 
        db: Session, 
        sender_id: UUID, 
        message_data: MessageCreate,
        background_tasks: Optional[Any] = None
    ) -> MessageResponse: # Ép kiểu trả về tường minh
        """
        Handle new message with WebSocket support for both Direct and Group chats
        """
        # (Import bên trong hàm để tránh Circular Import - Tốt)
        from app.services.websocket import websocket_manager as manager
        from app.services.notification_service import notification_service
        # Giả định có import NotificationCreate, NotificationType, NotificationPriority

        # ============================================================
        # 1. VALIDATION
        # ============================================================
        room_id = getattr(message_data, 'room_id', None)
        conversation_id = getattr(message_data, 'conversation_id', None) 
        real_room_id = room_id or conversation_id

        receiver_id = getattr(message_data, 'receiver_id', None)
        content = message_data.content
        
        if not content or not content.strip():
            raise APIException(status_code=400, code="MISSING_CONTENT", message="Message content is required")
        
        # ============================================================
        # 2. XÁC ĐỊNH PHÒNG CHAT & PHÂN QUYỀN
        # ============================================================
        if real_room_id:
            room = db.query(ChatRoom).filter(
                ChatRoom.id == real_room_id,
                ChatRoom.deleted_at.is_(None),
                ChatRoom.is_active.is_(True)
            ).first()

            if not room:
                raise APIException(status_code=404, code="ROOM_NOT_FOUND", message="Chat room not found")
            
            # Verify quyền
            if room.room_type in [MessageType.GROUP, MessageType.CLASS]:
                member = db.query(ChatRoomMember).filter(
                    ChatRoomMember.chat_room_id == real_room_id,
                    ChatRoomMember.user_id == sender_id
                ).first()
                if not member:
                    raise APIException(status_code=403, code="NOT_A_MEMBER", message="You are not a member of this chat")
            
            elif room.room_type == MessageType.DIRECT:
                if room.participant1_id != sender_id and room.participant2_id != sender_id:
                    raise APIException(status_code=403, code="NOT_A_PARTICIPANT", message="You are not a participant of this conversation")

        elif receiver_id:
            room = self._get_or_create_direct_room(db, sender_id, receiver_id)
        else:
            raise APIException(status_code=400, code="INVALID_TARGET", message="Either room_id or receiver_id must be provided")
        
        # ============================================================
        # 3. TÌM TARGET RECIPIENTS (SINGLE SOURCE OF TRUTH)
        # ============================================================
        target_recipient_ids = []
        
        if room.room_type == MessageType.DIRECT:
            other_user_id = room.participant2_id if room.participant1_id == sender_id else room.participant1_id
            if other_user_id:
                target_recipient_ids.append(other_user_id)
        
        elif room.room_type in [MessageType.GROUP, MessageType.CLASS]:
            members = db.query(ChatRoomMember).filter(ChatRoomMember.chat_room_id == room.id).all()
            target_recipient_ids = [m.user_id for m in members if m.user_id != sender_id]

        # ============================================================
        # 4. LƯU DATABASE (Message & Recipients)
        # ============================================================
        message_db_data = {
            "sender_id": sender_id,
            "chat_room_id": room.id,
            "content": content,
            "message_type": room.room_type.value if hasattr(room.room_type, 'value') else room.room_type,
            "status": MessageStatus.SENT.value,
            "attachments": getattr(message_data, 'attachments', []),
            "priority": getattr(message_data, 'priority', 'normal')
        }
        new_message = self.message_repo.create(db, obj_in=message_db_data)
        
        # Add for Sender (Đã đọc)
        self.recipient_repo.create(db, obj_in={
            "message_id": new_message.id,
            "recipient_id": sender_id,
            "recipient_type": "user",
            "read_at": datetime.now(timezone.utc)
        })

        # Add for Targets (Chưa đọc)
        recipient_type_str = "user" if room.room_type == MessageType.DIRECT else ("group" if room.room_type == MessageType.GROUP else "class")
        for uid in target_recipient_ids:
            self.recipient_repo.create(db, obj_in={
                "message_id": new_message.id,
                "recipient_id": uid,
                "recipient_type": recipient_type_str
            })
        
        room.last_message_at = new_message.created_at
        db.commit()

        # Load đầy đủ quan hệ để chuẩn bị trả về & gửi Notification
        new_message = db.query(Message).options(
            joinedload(Message.sender),
            joinedload(Message.chat_room)
        ).filter(Message.id == new_message.id).first()
        
        # ============================================================
        # 5. WEBSOCKET BROADCAST
        # ============================================================
        payload = {
            "type": "new_message",
            "message_id": str(new_message.id),
            "sender_id": str(sender_id),
            "room_id": str(room.id),
            "conversationId": str(room.id),
            "room_type": room.room_type.value if hasattr(room.room_type, 'value') else room.room_type,
            "content": content,
            "timestamp": new_message.created_at.isoformat() if new_message.created_at else datetime.now().isoformat(),
            "attachments": new_message.attachments or []
        }
        
        if room.room_type == MessageType.DIRECT:
            await manager.send_to_user(sender_id, payload)
            for uid in target_recipient_ids:
                await manager.send_to_user(uid, payload)
        
        elif room.room_type in [MessageType.GROUP, MessageType.CLASS]:
            await manager.broadcast_to_room(room_id=room.id, message=payload, db_session=db)
        
        # ============================================================
        # 6. BACKGROUND NOTIFICATIONS (ĐÃ TỐI ƯU TRUY VẤN)
        # ============================================================
        if background_tasks and target_recipient_ids:
            muted_user_ids = db.query(ChatRoomMember.user_id).filter(
                ChatRoomMember.chat_room_id == room.id,
                ChatRoomMember.user_id.in_(target_recipient_ids),
                ChatRoomMember.is_muted.is_(True)
            ).all()
            
            muted_set = {m[0] for m in muted_user_ids}
            final_notify_ids = [uid for uid in target_recipient_ids if uid not in muted_set]
            
            if final_notify_ids:
                # [OPTIMIZATION]: Tận dụng new_message.sender đã joinedload ở trên
                sender_name = f"{new_message.sender.first_name} {new_message.sender.last_name}".strip() if new_message.sender else "Ai đó"
                preview_content = content[:100] + "..." if len(content) > 100 else content

                if room.room_type == MessageType.DIRECT:
                    noti_title = f"{sender_name} đã gửi tin nhắn cho bạn"
                    action_url = f"/messages/direct/{sender_id}" 
                else:
                    group_name = getattr(room, 'title', 'Nhóm chat') or 'Nhóm chat'
                    noti_title = f"{sender_name} nhắn trong {group_name}"
                    action_url = f"/messages/group/{room.id}"

                for user_id_to_notify in final_notify_ids:
                    noti_data = NotificationCreate(
                        user_id=user_id_to_notify,
                        title=noti_title,
                        content=preview_content,
                        notification_type=NotificationType.MESSAGE_RECEIVED,
                        priority=NotificationPriority.NORMAL,
                        action_url=action_url,
                        data={
                            "room_id": str(room.id),
                            "message_id": str(new_message.id),
                            "sender_id": str(sender_id)
                        },
                        channels=["in_app"]
                    )
                    
                    background_tasks.add_task(
                        notification_service.send_notification, 
                        db, 
                        noti_data
                    )
        
        # ============================================================
        # 7. TRẢ VỀ DỮ LIỆU CHUẨN (Explicit Validation)
        # ============================================================
        return MessageResponse.model_validate(new_message, from_attributes=True)
    
    def _get_or_create_direct_room(self, db: Session, sender_id: UUID, receiver_id: UUID):
        """Get or create 1-1 chat room"""
        ids = sorted([str(sender_id), str(receiver_id)])
        p1_id, p2_id = UUID(ids[0]), UUID(ids[1])
        
        room = db.query(ChatRoom).filter(
            ChatRoom.room_type == MessageType.DIRECT,
            ChatRoom.participant1_id == p1_id,
            ChatRoom.participant2_id == p2_id
        ).first()
        
        if not room:
            room_data = {
                "room_type": MessageType.DIRECT.value,
                "participant1_id": p1_id,
                "participant2_id": p2_id,
                "title": "Direct Chat",
                "created_at": datetime.utcnow(),
                "created_by": sender_id
            }
            room = self.chat_room_repo.create(db, obj_in=room_data)
            db.flush()
        
        return room
    
message_sender_service = MessageSenderService()