import math
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, and_
from fastapi import HTTPException
from app.core.exceptions import APIException
from app.models.message import Message, ChatRoom, ChatRoomMember, MessageRecipient, MessageType, MemberRole
from app.models.audit_log import AuditAction
from app.schemas.base_schema import PaginationMetadata, PaginationResponse
from app.schemas.message import MessageResponse
from app.schemas.message import MessageResponse
from app.schemas.user import UserMiniResponse
from app.services.audit_log_service import audit_service
from app.services.websocket import websocket_manager
from app.repositories.message import recipient_repository
from datetime import datetime, timezone

class InteractionService:
    async def mark_conversation_as_read(self, db: Session, room_id: UUID, user_id: UUID):
        """Mark all messages in a conversation as read"""
        updated_count = recipient_repository.mark_room_as_read(db, user_id, room_id)
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

            member.last_cleared_at = datetime.now(timezone.utc)
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
    async def edit_message(
        self, 
        db: Session, 
        message_id: UUID, 
        new_content: str, 
        user_id: UUID
    ) -> MessageResponse:
        
        # 1. Lấy message kèm theo thông tin Room và Sender để map schema và gửi socket
        message = db.query(Message).options(
            joinedload(Message.sender),
            joinedload(Message.chat_room)
        ).filter(Message.id == message_id).first()
        
        if not message:
            raise APIException(status_code=404, code="MESSAGE_NOT_FOUND", message="Message not found")
        
        # 2. Check quyền: Chỉ sender mới được sửa
        if message.sender_id != user_id:
            raise APIException(status_code=403, code="FORBIDDEN_EDIT", message="You can only edit your own messages")
            
        # (Tùy chọn) Check thời gian: Không cho sửa sau 15 phút
        # Nếu muốn bật, hãy uncomment đoạn này:
        # time_diff = datetime.now(timezone.utc) - message.created_at.replace(tzinfo=timezone.utc)
        # if time_diff.total_seconds() > 900: # 15 phút = 900 giây
        #     raise APIException(status_code=400, code="EDIT_TIMEOUT", message="Cannot edit message older than 15 minutes")

        # 3. Cập nhật Database
        message.content = new_content
        message.updated_at = func.now()
        
        db.commit()
        db.refresh(message)
        
        # 4. Ép kiểu sang Pydantic Model một cách tường minh
        msg_resp = MessageResponse(
            id=message.id,
            sender_id=message.sender_id,
            chat_room_id=message.chat_room_id,
            sender=UserMiniResponse(
                id=message.sender.id,
                full_name=f"{message.sender.first_name} {message.sender.last_name}",
                email=message.sender.email,
                avatar_url=message.sender.avatar_url
            ) if message.sender else None,
            message_type=message.message_type.value if hasattr(message.message_type, 'value') else message.message_type,
            content=message.content,
            attachments=message.attachments or [],
            priority=message.priority.value if hasattr(message.priority, 'value') else message.priority,
            status=message.status.value if hasattr(message.status, 'value') else message.status,
            created_at=message.created_at,
            updated_at=message.updated_at,
            
            # Đã chỉnh sửa thành công, cờ is_edited = True
            is_edited=True,
            is_read=True, # Bản thân người gửi mặc định là đã đọc
            is_starred=False
        )
        
        # ============================================================
        # 5. WEBSOCKET BROADCAST TỚI CÁC CLIENT
        # ============================================================
        room = message.chat_room
        payload = {
            "type": "message_updated",
            "message_id": str(message.id),
            "room_id": str(room.id),
            "new_content": new_content,
            "updated_at": message.updated_at.isoformat() if message.updated_at else datetime.now().isoformat()
        }
        
        if room.room_type == MessageType.DIRECT:
            # Gửi cho cả 2 người trong đoạn chat 1-1
            target_ids = [room.participant1_id, room.participant2_id]
            for uid in target_ids:
                if uid:
                    await websocket_manager.send_to_user(uid, payload)
        else:
            # Gửi cho toàn bộ phòng Group/Class
            await websocket_manager.broadcast_to_room(
                room_id=room.id,
                message=payload,
                db_session=db
            )
        
        return msg_resp

    # --- 2. Search Messages ---
    async def search_messages(
        self, 
        db: Session, 
        query_text: str, 
        user_id: UUID, 
        room_id: Optional[UUID] = None, 
        page: int = 1,     
        limit: int = 20
    ) -> PaginationResponse[MessageResponse]:
        
        skip = (page - 1) * limit
        
        # ==========================================
        # 1. BẢO MẬT: TÌM DANH SÁCH PHÒNG ĐƯỢC PHÉP TRUY CẬP
        # ==========================================
        # Phòng Group/Class
        user_room_ids = db.query(ChatRoomMember.chat_room_id).filter(
            ChatRoomMember.user_id == user_id,
            ChatRoomMember.chat_room.has(ChatRoom.deleted_at.is_(None)),
            ChatRoomMember.chat_room.has(ChatRoom.is_active.is_(True))
        ).subquery()
        
        # Phòng Direct (1-1)
        direct_room_ids = db.query(ChatRoom.id).filter(
            ChatRoom.room_type == MessageType.DIRECT,
            or_(ChatRoom.participant1_id == user_id, ChatRoom.participant2_id == user_id),
            ChatRoom.deleted_at.is_(None),
            ChatRoom.is_active.is_(True)
        ).subquery()

        # ==========================================
        # 2. XÂY DỰNG CÂU LỆNH TÌM KIẾM MESSAGE
        # ==========================================
        q = db.query(Message).options(
            joinedload(Message.sender) # QUAN TRỌNG: Chống N+1 Query
        ).filter(
            Message.content.ilike(f"%{query_text}%"), # Tìm kiếm không phân biệt hoa thường
            or_(
                Message.chat_room_id.in_(user_room_ids),
                Message.chat_room_id.in_(direct_room_ids)
            )
        )
        
        if room_id:
            # Nếu truyền room_id, thu hẹp phạm vi tìm kiếm lại
            q = q.filter(Message.chat_room_id == room_id)
            
        # ==========================================
        # 3. METADATA VÀ PHÂN TRANG
        # ==========================================
        total = q.count()
        meta = PaginationMetadata(
            page=page,
            limit=limit,
            total=total,
            total_pages=math.ceil(total / limit) if limit > 0 else 1
        )
        
        messages_db = q.order_by(Message.created_at.desc()).offset(skip).limit(limit).all()
        
        if not messages_db:
            return PaginationResponse(data=[], meta=meta)

        # ==========================================
        # 4. ÉP KIỂU VÀ TRẢ VỀ DỮ LIỆU CHUẨN
        # ==========================================
        # (Tùy chọn) Lấy trạng thái đã đọc/chưa đọc nếu bạn muốn hiển thị ở màn hình Search
        message_ids = [msg.id for msg in messages_db]
        sparse_statuses = recipient_repository.get_statuses_for_user(db, user_id, message_ids)

        results = []
        for msg in messages_db:
            status = sparse_statuses.get(msg.id, {})
            
            # Bỏ qua các tin nhắn mà user đã chủ động xóa
            if status.get("deleted"):
                continue

            sender_mini = None
            if msg.sender:
                sender_mini = UserMiniResponse(
                    id=msg.sender.id,
                    full_name=f"{msg.sender.first_name} {msg.sender.last_name}",
                    email=msg.sender.email,
                    avatar_url=msg.sender.avatar_url
                )

            msg_resp = MessageResponse(
                id=msg.id,
                sender_id=msg.sender_id,
                chat_room_id=msg.chat_room_id,
                sender=sender_mini,
                
                message_type=msg.message_type.value if hasattr(msg.message_type, 'value') else msg.message_type,
                content=msg.content,
                attachments=msg.attachments or [],
                priority=msg.priority.value if hasattr(msg.priority, 'value') else msg.priority,
                status=msg.status.value if hasattr(msg.status, 'value') else msg.status,
                created_at=msg.created_at,
                updated_at=msg.updated_at,
                
                # Các cờ phụ trợ UI
                is_read=status.get("read_at") is not None,
                is_starred=status.get("starred", False),
                is_edited=(msg.updated_at != msg.created_at)
            )
            results.append(msg_resp)

        return PaginationResponse(
            data=results,
            meta=meta
        )

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
    
    def get_total_unread_count(self, db: Session, user_id: UUID) -> int:
        """
        Get total unread message count across all conversations, 
        EXCLUDING muted conversations, deleted messages, and deleted rooms.
        """
        total_unread = (
            db.query(func.count(MessageRecipient.id))
            .join(Message, Message.id == MessageRecipient.message_id)
            .join(ChatRoom, ChatRoom.id == Message.chat_room_id)
            .outerjoin(
                ChatRoomMember,
                and_(
                    ChatRoomMember.chat_room_id == Message.chat_room_id,
                    ChatRoomMember.user_id == user_id
                )
            )
            .filter(
                # Điều kiện của người nhận
                MessageRecipient.recipient_id == user_id,
                MessageRecipient.read_at.is_(None),
                MessageRecipient.deleted.is_(False),
                
                # Điều kiện của phòng chat
                ChatRoom.deleted_at.is_(None),        
                ChatRoom.is_active.is_(True),
                
                or_(
                    ChatRoomMember.is_muted.is_(False),
                    ChatRoomMember.is_muted.is_(None)
                )
            )
            .scalar()
        )
        
        return total_unread or 0
    
message_interaction_service = InteractionService()