from uuid import UUID
from typing import Optional, Any
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timezone
from fastapi import HTTPException

# Import Models & Schemas
from app.models.message import Message, ChatRoom, ChatRoomMember, MessageType, MessageStatus
from app.models.user import User
from app.models.notification import NotificationType, NotificationPriority
from app.schemas.message import MessageCreate
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
        ):
            """
            Handle new message with WebSocket support for both Direct and Group chats
            FIXED:
            - Determine participants strictly from Room data (Single Source of Truth)
            - Fix Broadcast logic for Direct Chat
            """

            from app.services.websocket import websocket_manager as manager
            from app.services.notification import notification_service

            # Validate input
            room_id = getattr(message_data, 'room_id', None)
            conversation_id = getattr(message_data, 'conversation_id', None) # Support alias
            real_room_id = room_id or conversation_id

            receiver_id = getattr(message_data, 'receiver_id', None)
            content = message_data.content
            
            if not content:
                raise ValueError("Message content is required")
            
            # Determine chat type and get/create room
            if real_room_id:
                # GROUP/CLASS/EXISTING DIRECT CHAT - Room already exists
                room = db.query(ChatRoom).filter(
                    ChatRoom.id == real_room_id,
                    ChatRoom.deleted_at.is_(None),
                    ChatRoom.is_active.is_(True)
                ).first()

                if not room:
                    raise HTTPException(status_code=404, detail="Chat room not found")
                
                # Verify sender is a member/participant
                if room.room_type in [MessageType.GROUP, MessageType.CLASS]:
                    member = db.query(ChatRoomMember).filter(
                        ChatRoomMember.chat_room_id == real_room_id,
                        ChatRoomMember.user_id == sender_id
                    ).first()
                    if not member:
                        raise HTTPException(status_code=403, detail="You are not a member of this chat")
                elif room.room_type == MessageType.DIRECT:
                    if room.participant1_id != sender_id and room.participant2_id != sender_id:
                        raise HTTPException(status_code=403, detail="You are not a participant of this conversation")

            elif receiver_id:
                # NEW DIRECT CHAT - Get or create room
                room = self._get_or_create_direct_room(db, sender_id, receiver_id)
            
            else:
                raise ValueError("Either conversation_id/room_id or receiver_id must be provided")
            
            # --- [CRITICAL FIX START] --- 
            # Xác định chính xác danh sách người nhận (Target Recipients) từ dữ liệu Room
            target_recipient_ids = []
            
            if room.room_type == MessageType.DIRECT:
                # Với Direct Chat: Người nhận là người KHÁC sender trong phòng
                other_user_id = room.participant2_id if room.participant1_id == sender_id else room.participant1_id
                if other_user_id:
                    target_recipient_ids.append(other_user_id)
            
            elif room.room_type in [MessageType.GROUP, MessageType.CLASS]:
                # Với Group Chat: Người nhận là tất cả thành viên (trừ sender)
                members = db.query(ChatRoomMember).filter(
                    ChatRoomMember.chat_room_id == room.id
                ).all()
                target_recipient_ids = [m.user_id for m in members if m.user_id != sender_id]
            # --- [CRITICAL FIX END] ---

            # Save message to database
            message_db_data = {
                "sender_id": sender_id,
                "chat_room_id": room.id,
                "content": content,
                "message_type": room.room_type.value,
                "status": MessageStatus.SENT.value,
                "attachments": getattr(message_data, 'attachments', []),
                "priority": getattr(message_data, 'priority', 'normal')
            }
            new_message = self.message_repo.create(db, obj_in=message_db_data)
            
            # Create recipient records
            # 1. Add for Sender (để sender cũng có record trong lịch sử)
            self.recipient_repo.create(db, obj_in={
                "message_id": new_message.id,
                "recipient_id": sender_id,
                "recipient_type": "user",
                "read_at": datetime.now(timezone.utc)  # Mark as read for sender
            })

            # 2. Add for Recipients (FIXED: dùng danh sách đã tính toán ở trên)
            recipient_type_str = "user" if room.room_type == MessageType.DIRECT else ("group" if room.room_type == MessageType.GROUP else "class")
            for uid in target_recipient_ids:
                self.recipient_repo.create(db, obj_in={
                    "message_id": new_message.id,
                    "recipient_id": uid,
                    "recipient_type": recipient_type_str
                })
            
            # Update room's last_message_at
            room.last_message_at = new_message.created_at
            
            db.commit()

            new_message = db.query(Message).options(
                joinedload(Message.sender),
                joinedload(Message.chat_room)
            ).filter(Message.id == new_message.id).first()
            
            # Prepare WebSocket payload
            payload = {
                "type": "new_message",
                "message_id": str(new_message.id),
                "sender_id": str(sender_id),
                "room_id": str(room.id),
                "conversationId": str(room.id), # Support frontend convention
                "room_type": room.room_type.value,
                "content": content,
                "timestamp": new_message.created_at.isoformat(),
                "attachments": new_message.attachments or []
            }
            
            # --- [BROADCAST LOGIC FIXED] ---
            if room.room_type == MessageType.DIRECT:
                # Gửi cho chính mình (Sender)
                await manager.send_to_user(sender_id, payload)
                
                # Gửi cho người nhận (Target) - Dùng ID chuẩn xác từ DB
                for uid in target_recipient_ids:
                    await manager.send_to_user(uid, payload)
            
            elif room.room_type in [MessageType.GROUP, MessageType.CLASS]:
                # Broadcast cho cả phòng (bao gồm cả sender để đồng bộ nếu cần)
                await manager.broadcast_to_room(
                    room_id=room.id,
                    message=payload,
                    db_session=db
                )
            # -------------------------------
            
            # Handle Notifications (Background Task)
            if background_tasks and target_recipient_ids:
                # --- Check Mute status ---
                muted_user_ids = db.query(ChatRoomMember.user_id).filter(
                    ChatRoomMember.chat_room_id == room.id,
                    ChatRoomMember.user_id.in_(target_recipient_ids),
                    ChatRoomMember.is_muted.is_(True)
                ).all()
                
                # Convert list of tuples to set of UUIDs
                muted_set = {m[0] for m in muted_user_ids}
                
                final_notify_ids = [uid for uid in target_recipient_ids if uid not in muted_set]
                
                if final_notify_ids:
                    sender_user = db.query(User).filter(User.id == sender_id).first()
                    sender_name = (sender_user.first_name + " " + sender_user.last_name) if sender_user else "Someone"
                    
                    preview_content = content[:100] + "..." if len(content) > 100 else content

                    if room.room_type == MessageType.DIRECT:
                        noti_title = f"{sender_name} đã gửi tin nhắn cho bạn"
                        action_url = f"/messages/direct/{sender_id}" 
                    else:
                        group_name = getattr(room, 'title', 'Nhóm chat') or 'Nhóm chat'
                        noti_title = f"{sender_name} nhắn trong {group_name}"
                        action_url = f"/messages/group/{room.id}"

                    # Chỉ gửi cho danh sách đã lọc (final_notify_ids)
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
            
            return new_message
    
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