from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from fastapi import HTTPException
from app.models.message import Message, ChatRoom, ChatRoomMember, MessageRecipient, MessageType, MemberRole
from app.models.audit_log import AuditAction
from app.services.audit_log import audit_service
from datetime import datetime, timezone

class InteractionService:
    async def mark_conversation_as_read(self, db: Session, room_id: UUID, user_id: UUID):
        """Mark all messages in a conversation as read"""
        updated_count = self.recipient_repo.mark_room_as_read(db, user_id, room_id)
        db.commit()
        return {
            "success": True,
            "room_id": str(room_id),
            "marked_count": updated_count
        }
    
    async def delete_chat_room(
        self,
        db: Session,
        room_id: UUID,
        current_user_id: UUID
    ):
        room = db.query(ChatRoom).filter(
            ChatRoom.id == room_id,
            ChatRoom.deleted_at.is_(None)
        ).first()

        if not room:
            raise HTTPException(status_code=404, detail="Chat room not found")

        # --- DIRECT CHAT ---
        if room.room_type == MessageType.DIRECT:
            if current_user_id not in [room.participant1_id, room.participant2_id]:
                raise HTTPException(403, "You are not a participant")

            # Lưu mốc "xóa chat" cho user hiện tại
            member = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room_id,
                ChatRoomMember.user_id == current_user_id
            ).first()

            # Direct chat chưa có member → tạo record
            if not member:
                member = ChatRoomMember(
                    chat_room_id=room_id,
                    user_id=current_user_id
                )
                db.add(member)

            member.last_read_at = datetime.now(timezone.utc)  # ⬅️ mốc clear chat
            db.commit()

            return {
                "success": True,
                "room_id": str(room_id),
                "scope": "self",
                "message": "Chat cleared for you"
            }

        # --- GROUP / CLASS ---
        else:
            member = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room_id,
                ChatRoomMember.user_id == current_user_id
            ).first()

            if not member:
                raise HTTPException(status_code=403, detail="You are not a member of this chat")

            if member.role != MemberRole.ADMIN:
                raise HTTPException(
                    status_code=403,
                    detail="Only admins can delete this chat room"
                )

        # --- SOFT DELETE ---
        room.is_active = False
        room.deleted_at = func.now()

        audit_service.log(
            db=db,
            action=AuditAction.DELETE,
            table_name="chat_rooms",
            record_id=room.id,
            user_id=current_user_id,
            old_values={"is_active": True},
            new_values={"is_active": False}
        )

        db.commit()
        return {
            "success": True,
            "room_id": str(room_id),
            "message": "Chat room deleted successfully"
        }
    
    async def toggle_mute(self, db: Session, room_id: UUID, user_id: UUID, mute: bool):
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == user_id
        ).first()
        if member:
            member.is_muted = mute # Giả định model đã có field này
            db.commit()
        return {"success": True, "is_muted": mute}
    
    # --- 1. Edit Message ---
    async def edit_message(self, db: Session, message_id: UUID, new_content: str, user_id: UUID):
        # Lấy message
        message = db.query(Message).filter(Message.id == message_id).first()
        if not message:
            raise HTTPException(404, "Message not found")
        
        # Check quyền: Chỉ sender mới được sửa
        if message.sender_id != user_id:
            raise HTTPException(403, "You can only edit your own messages")
            
        # (Optional) Check thời gian: Không cho sửa sau 15 phút
        # time_diff = datetime.now(timezone.utc) - message.created_at
        # if time_diff.total_seconds() > 900:
        #     raise HTTPException(400, "Cannot edit message older than 15 minutes")

        # Update
        message.content = new_content
        message.updated_at = func.now()
        
        db.commit()
        db.refresh(message)
        
        # (Optional) Broadcast socket event 'message_updated' tại đây
        
        return message

    # --- 2. Search Messages ---
    async def search_messages(
        self, 
        db: Session, 
        query_text: str, 
        user_id: UUID, 
        room_id: Optional[UUID] = None, 
        skip: int = 0, 
        limit: int = 20
    ):
        # Query cơ bản: Tìm trong bảng Message
        # Join MessageRecipient để đảm bảo user có quyền xem message đó (đã nhận/gửi)
        # Cách đơn giản nhất: Search message trong các room mà user là thành viên
        
        # Lấy danh sách room user đang tham gia
        user_room_ids = db.query(ChatRoomMember.chat_room_id).filter(
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.chat_room.has(ChatRoom.deleted_at.is_(None)),
            ChatRoomMember.chat_room.has(ChatRoom.is_active.is_(True))
        ).subquery()
        
        direct_room_ids = db.query(ChatRoom.id).filter(
            ChatRoom.room_type == MessageType.DIRECT,
            or_(ChatRoom.participant1_id == user_id, ChatRoom.participant2_id == user_id)
        ).subquery()

        # Build Main Query
        q = db.query(Message).filter(
            Message.content.ilike(f"%{query_text}%"), # Case-insensitive search
            or_(
                Message.chat_room_id.in_(user_room_ids),
                Message.chat_room_id.in_(direct_room_ids)
            )
        )
        
        if room_id:
            # Nếu user muốn search cụ thể trong 1 room
            q = q.filter(Message.chat_room_id == room_id)
            
        total = q.count()
        results = q.order_by(Message.created_at.desc()).offset(skip).limit(limit).all()
        
        return {
            "total": total,
            "results": results # Cần map sang MessageResponse
        }

    async def delete_message(self, db: Session, message_id: UUID, user_id: UUID):
        # Chỉ xóa phía người nhận (MessageRecipient) hoặc xóa gốc nếu là sender?
        recipient_record = db.query(MessageRecipient).filter(
            MessageRecipient.message_id == message_id,
            MessageRecipient.recipient_id == user_id
        ).first()
        
        if recipient_record:
            recipient_record.deleted = True
            db.commit()
            return {"success": True}
        return {"success": False, "detail": "Message not found"}
    
    def get_total_unread_count(self, db: Session, user_id: UUID):
        """
        Get total unread message count across all conversations, 
        EXCLUDING muted conversations.
        """
        # Join MessageRecipient -> Message -> ChatRoomMember (để check mute)
        # Sử dụng outerjoin với ChatRoomMember vì Direct Chat có thể chưa có record trong bảng Member
        
        total_unread = (
            db.query(func.count(MessageRecipient.id))
            .join(Message, Message.id == MessageRecipient.message_id)
            .outerjoin(
                ChatRoomMember,
                and_(
                    ChatRoomMember.chat_room_id == Message.chat_room_id,
                    ChatRoomMember.user_id == user_id
                )
            )
            .filter(
                MessageRecipient.recipient_id == user_id,
                MessageRecipient.read_at.is_(None),
                # Chỉ đếm nếu user KHÔNG mute (is_muted là False hoặc NULL)
                or_(
                    ChatRoomMember.is_muted.is_(False),
                    ChatRoomMember.is_muted.is_(None)
                )
            )
            .scalar()
        )
        
        return total_unread
    
message_interaction_service = InteractionService()