from app.repositories.message import (
    message_repository, 
    recipient_repository, 
    chat_room_repository
)
from app.repositories.user import user_repository
from app.services.websocket import manager
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from uuid import UUID
from typing import Dict, Any, List, Optional
from app.schemas.message import MessageCreate, ConversationResponse, GroupCreateRequest, GroupUpdateRequest
from app.models.message import Message, ChatRoom, ChatRoomMember, MessageType, MessageStatus, MemberRole, MessageRecipient
from fastapi import HTTPException
import logging
from app.schemas.notification import NotificationCreate
from app.models.notification import NotificationType, NotificationPriority
from app.services.notification import notification_service
from app.models.user import User
from fastapi import UploadFile
from datetime import datetime, timezone

from app.services.cloudinary import upload_and_save_metadata

logger = logging.getLogger(__name__)


class MessageService:
    def __init__(self):
        self.message_repo = message_repository
        self.recipient_repo = recipient_repository
        self.chat_room_repo = chat_room_repository
        self.user_repo = user_repository
    
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
                "title": "Direct Chat"
            }
            room = self.chat_room_repo.create(db, obj_in=room_data)
            db.flush()
        
        return room
    
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

            # Gửi noti cho danh sách target_recipient_ids (đã loại trừ sender)
            for user_id_to_notify in target_recipient_ids:
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
    
    async def get_user_conversations(
        self, 
        db: Session, 
        user_id: UUID
    ) -> List[ConversationResponse]:
        """
        Get list of ALL conversations for a user (Direct + Group + Class)
        OPTIMIZED: Solves N+1 Query problem using Joins and Subqueries.
        """
        from sqlalchemy import func, or_, and_, distinct
        from sqlalchemy.orm import aliased
        from app.models.message import MessageRecipient
        
        # 1. Subquery: Lấy tin nhắn cuối cùng của mỗi phòng (Dùng DISTINCT ON của Postgres)
        last_msg_sub = (
            db.query(
                Message.chat_room_id,
                Message.id,
                Message.content,
                Message.sender_id,
                Message.created_at
            )
            .distinct(Message.chat_room_id)
            .order_by(Message.chat_room_id, Message.created_at.desc())
            .subquery()
        )

        # 2. Subquery: Đếm số tin nhắn chưa đọc của user hiện tại trong mỗi phòng
        unread_sub = (
            db.query(
                Message.chat_room_id,
                func.count(MessageRecipient.id).label("unread_count")
            )
            .join(MessageRecipient, Message.id == MessageRecipient.message_id)
            .filter(
                MessageRecipient.recipient_id == user_id,
                MessageRecipient.read_at.is_(None)
            )
            .group_by(Message.chat_room_id)
            .subquery()
        )

        # 3. Subquery: Đếm tổng thành viên trong mỗi phòng (cho Group/Class)
        member_count_sub = (
            db.query(
                ChatRoomMember.chat_room_id,
                func.count(ChatRoomMember.user_id).label("member_count")
            )
            .group_by(ChatRoomMember.chat_room_id)
            .subquery()
        )

        # 4. Subquery: Lấy danh sách ID các phòng mà user là thành viên (Group membership)
        user_membership_sub = (
            db.query(ChatRoomMember.chat_room_id)
            .filter(ChatRoomMember.user_id == user_id)
            .subquery()
        )

        # 5. Alias cho User để join lấy thông tin người chat cùng (Direct Chat)
        # Cần 2 alias vì trong Direct chat user có thể là participant1 hoặc participant2
        User1 = aliased(User, name="u1")
        User2 = aliased(User, name="u2")

        # 6. MAIN QUERY: Join tất cả lại với nhau
        results = (
            db.query(
                ChatRoom,
                last_msg_sub.c.id.label("last_msg_id"),
                last_msg_sub.c.content.label("last_msg_content"),
                last_msg_sub.c.sender_id.label("last_msg_sender"),
                last_msg_sub.c.created_at.label("last_msg_time"),
                func.coalesce(unread_sub.c.unread_count, 0).label("unread_count"),
                func.coalesce(member_count_sub.c.member_count, 0).label("member_count"),
                User1, # user ứng với participant1
                User2  # user ứng với participant2
            )
            .outerjoin(last_msg_sub, ChatRoom.id == last_msg_sub.c.chat_room_id)
            .outerjoin(unread_sub, ChatRoom.id == unread_sub.c.chat_room_id)
            .outerjoin(member_count_sub, ChatRoom.id == member_count_sub.c.chat_room_id)
            .outerjoin(User1, ChatRoom.participant1_id == User1.id)
            .outerjoin(User2, ChatRoom.participant2_id == User2.id)
            .filter(
                ChatRoom.deleted_at.is_(None),
                ChatRoom.is_active.is_(True),
                or_(
                    # Điều kiện 1: Là Direct chat và user nằm trong participant1 hoặc participant2
                    and_(
                        ChatRoom.room_type == MessageType.DIRECT,
                        or_(ChatRoom.participant1_id == user_id, ChatRoom.participant2_id == user_id)
                    ),
                    # Điều kiện 2: Là Group chat và user là thành viên
                    ChatRoom.id.in_(user_membership_sub)
                )
            )
            # Sắp xếp theo tin nhắn mới nhất, nếu không có thì lấy ngày tạo phòng
            .order_by(ChatRoom.last_message_at.desc().nulls_last(), ChatRoom.created_at.desc())
            .all()
        )

        # 7. Map kết quả từ DB ra Schema Response
        conversations = []
        for row in results:
            room = row.ChatRoom
            
            # Mặc định lấy info từ room (cho Group/Class)
            title = room.title
            avatar_url = room.avatar_url
            description = room.description
            member_count = row.member_count # Lấy từ subquery count
            
            # ✅ LOGIC MAPPING QUAN TRỌNG CHO DIRECT CHAT
            if room.room_type == MessageType.DIRECT:
                # Direct chat: Title/Avatar phải là của người kia
                other_user = row.u2 if room.participant1_id == user_id else row.u1
                
                if other_user:
                    title = f"{other_user.first_name} {other_user.last_name}"
                    avatar_url = other_user.avatar_url
                    # Direct chat không có description, có thể để trống hoặc hiển thị trạng thái
                    description = None 
                else:
                    title = "Unknown User"
                    avatar_url = None
                
                member_count = 2 # Direct luôn là 2 người
            
            # Map Last Message
            last_message_obj = None
            if row.last_msg_id:
                last_message_obj = {
                    "message_id": str(row.last_msg_id),
                    "content": row.last_msg_content,
                    "sender_id": str(row.last_msg_sender),
                    "timestamp": row.last_msg_time, # Pydantic tự serialize datetime
                }

            conversations.append(ConversationResponse(
                room_id=room.id,
                room_type=room.room_type.value,
                title=title or "No Title",
                
                # ✅ Các field mới đã được map
                avatar_url=avatar_url,      
                description=description,
                member_count=member_count,
                
                last_message=last_message_obj,
                last_message_at=room.last_message_at,
                unread_count=row.unread_count
            ))
            
        return conversations
    
    async def get_or_create_direct_conversation(
        self, 
        db: Session, 
        user_id: UUID, 
        other_user_id: UUID
    ) -> Dict[str, Any]:
        """Get or create a direct conversation between two users"""
        ids = sorted([str(user_id), str(other_user_id)])
        room = db.query(ChatRoom).filter(
            ChatRoom.room_type == MessageType.DIRECT,
            ChatRoom.participant1_id == UUID(ids[0]),
            ChatRoom.participant2_id == UUID(ids[1]),
            ChatRoom.deleted_at.is_(None),
            ChatRoom.is_active.is_(True)
        ).first()
        
        # Get other user info
        other_user = self.user_repo.get(db, id=other_user_id)
        
        last_message = db.query(Message).filter(
            Message.chat_room_id == room.id
        ).order_by(Message.created_at.desc()).first()
        
        return {
            "room_id": str(room.id),
            "room_type": room.room_type.value,
            "title": (other_user.first_name + " " + other_user.last_name) if other_user else "Unknown User",
            "avatar_url": getattr(other_user, 'avatar_url', None) if other_user else None,
            "last_message": {
                "message_id": str(last_message.id) if last_message else None,
                "content": last_message.content if last_message else None,
                "timestamp": last_message.created_at.isoformat() if last_message else None
            } if last_message else None
        }
    
    async def get_chat_history(
        self, 
        db: Session, 
        room_id: UUID, 
        current_user_id: UUID, 
        skip: int = 0, 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        room = db.query(ChatRoom).filter(
            ChatRoom.id == room_id,
            ChatRoom.deleted_at.is_(None),
            ChatRoom.is_active.is_(True)
        ).first()

        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

        # =====================
        # CHECK ACCESS
        # =====================
        member = None
        if room.room_type == MessageType.DIRECT:
            if current_user_id not in [room.participant1_id, room.participant2_id]:
                raise HTTPException(403, "Access denied")

            member = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room_id,
                ChatRoomMember.user_id == current_user_id
            ).first()
        else:
            member = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room_id,
                ChatRoomMember.user_id == current_user_id
            ).first()

            if not member:
                raise HTTPException(403, "Access denied")

        # =====================
        # BUILD MESSAGE QUERY
        # =====================
        query = db.query(Message).options(
            joinedload(Message.sender)
        ).filter(
            Message.chat_room_id == room_id
        )

        # ⬅️ CORE LOGIC: chỉ lấy message sau mốc clear/read
        if member and member.last_read_at:
            query = query.filter(
                Message.created_at > member.last_read_at
            )

        messages_db = (
            query
            .order_by(Message.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        if not messages_db:
            return []

        message_ids = [msg.id for msg in messages_db]

        sparse_statuses = self.recipient_repo.get_statuses_for_user(
            db, current_user_id, message_ids
        )

        history = []
        for msg in messages_db:
            status = sparse_statuses.get(msg.id, {})

            if status.get("deleted"):
                continue

            sender_name = "System"
            if msg.sender:
                sender_name = f"{msg.sender.first_name} {msg.sender.last_name}"

            history.append({
                "message_id": str(msg.id),
                "sender_id": str(msg.sender_id) if msg.sender_id else None,
                "sender_name": sender_name,
                "content": msg.content,
                "message_type": msg.message_type.value,
                "timestamp": msg.created_at.isoformat(),
                "attachments": msg.attachments or [],
                "is_read": status.get("read_at") is not None,
                "is_starred": status.get("starred", False)
            })

        history.reverse()
        return history

    
    async def mark_conversation_as_read(self, db: Session, room_id: UUID, user_id: UUID):
        """Mark all messages in a conversation as read"""
        updated_count = self.recipient_repo.mark_room_as_read(db, user_id, room_id)
        return {
            "success": True,
            "room_id": str(room_id),
            "marked_count": updated_count
        }
    
    # ========================
    # GROUP CHAT METHODS
    # ========================
    
    async def create_group_chat(
        self, 
        db: Session, 
        creator_id: UUID, 
        group_data: GroupCreateRequest,
        avatar: Optional[UploadFile] = None
    ):
        """Create a new group chat"""
        try:
            # Validate: creator must be in member list or add automatically
            member_ids = set(group_data.member_ids)
            member_ids.add(creator_id)  # Ensure creator is included
            
            # Validate: at least 2 members (including creator) for a group
            if len(member_ids) < 2:
                raise HTTPException(
                    status_code=400, 
                    detail="Group must have at least 2 members"
                )
            
            # Validate: all users exist
            for user_id in member_ids:
                user = self.user_repo.get(db, id=user_id)
                if not user:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"User {user_id} not found"
                    )
                
            # Handle avatar upload if provided
            if avatar:
                upload_result = await upload_and_save_metadata(
                    uploaded_file=avatar,
                    db=db,
                    user_id=creator_id,
                    folder="group_avatars"
                )
                avatar_url = upload_result.file_path
            
            # Create chat room
            chat_room = ChatRoom(
                room_type=MessageType.GROUP,
                title=group_data.title,
                description=group_data.description,
                avatar_url=avatar_url,
                created_by=creator_id,
                is_active=True
            )
            db.add(chat_room)
            db.flush()
            
            # Add creator as admin
            creator_member = ChatRoomMember(
                chat_room_id=chat_room.id,
                user_id=creator_id,
                role=MemberRole.ADMIN
            )
            db.add(creator_member)
            
            # Add other members
            for user_id in member_ids:
                if user_id != creator_id:
                    member = ChatRoomMember(
                        chat_room_id=chat_room.id,
                        user_id=user_id,
                        role=MemberRole.MEMBER
                    )
                    db.add(member)
        
            creator = self.user_repo.get(db, id=creator_id)
            creator_name = (creator.first_name + " " + creator.last_name) if creator else "Someone"
            # Send system message
            await self._send_system_message(
                db, 
                chat_room.id, 
                f"Group '{chat_room.title}' was created by {creator_name}"
            )

            db.commit()
            db.refresh(chat_room)
            
            return chat_room
        except Exception as e:
                db.rollback()
                logger.error(f"Error creating group chat: {e}")
                raise e
    
    async def add_members_to_group(
        self,
        db: Session,
        room_id: UUID,
        adder_id: UUID,
        user_ids: List[UUID]
    ):
        """Add members to group chat"""
        # Get room
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Group not found")
        
        # Check if adder is admin/moderator
        adder_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == adder_id
        ).first()
        
        if not adder_member or adder_member.role not in [MemberRole.ADMIN, MemberRole.MODERATOR]:
            raise HTTPException(status_code=403, detail="Only admins/moderators can add members")
        
        # Validate users exist
        for user_id in user_ids:
            user = self.user_repo.get(db, id=user_id)
            if not user:
                raise HTTPException(status_code=404, detail=f"User {user_id} not found")
        
        # Add new members
        added_members = []
        for user_id in user_ids:
            existing = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room_id,
                ChatRoomMember.user_id == user_id
            ).first()
            
            if not existing:
                member = ChatRoomMember(
                    chat_room_id=room_id,
                    user_id=user_id,
                    role=MemberRole.MEMBER
                )
                db.add(member)
                added_members.append(user_id)
        
        db.commit()
        
        # Send system message and notifications
        if added_members:
            await self._send_system_message(
                db,
                room_id,
                f"{len(added_members)} member(s) were added to the group"
            )
            
            await manager.notify_member_added(
                room_id=room_id,
                added_user_ids=added_members,
                added_by_user_id=adder_id,
                room_title=room.title
            )
        
        return {"added_count": len(added_members), "added_user_ids": [str(uid) for uid in added_members]}
    
    async def remove_member_from_group(
        self,
        db: Session,
        room_id: UUID,
        remover_id: UUID,
        user_id_to_remove: UUID
    ):
        """Remove a member from group"""
        # Get room
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Group not found")
        
        # Check permissions
        remover_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == remover_id
        ).first()
        
        # Allow if: (1) Admin removing anyone, or (2) User leaving themselves
        is_admin = remover_member and remover_member.role == MemberRole.ADMIN
        is_self_leave = remover_id == user_id_to_remove
        
        if not (is_admin or is_self_leave):
            raise HTTPException(
                status_code=403, 
                detail="Only admins can remove members, or you can leave yourself"
            )
        
        # Remove member
        member_to_remove = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == user_id_to_remove
        ).first()
        
        if not member_to_remove:
            raise HTTPException(status_code=404, detail="Member not found in this group")
        
        # Prevent removing the last admin
        if member_to_remove.role == MemberRole.ADMIN:
            admin_count = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room_id,
                ChatRoomMember.role == MemberRole.ADMIN
            ).count()
            
            if admin_count <= 1:
                raise HTTPException(
                    status_code=400, 
                    detail="Cannot remove the last admin. Promote another member first."
                )
        db.delete(member_to_remove)
        db.commit()
        
        deleted_user = self.user_repo.get(db, id=user_id_to_remove)
        deleted_user_name = (deleted_user.first_name + " " + deleted_user.last_name) if deleted_user else "Someone"
        
        # Send notifications
        action = "left" if is_self_leave else "was removed from"
        await self._send_system_message(
            db,
            room_id,
            f"{deleted_user_name} {action} the group"
        )
        
        await manager.notify_member_removed(
            room_id=room_id,
            removed_user_id=user_id_to_remove,
            removed_by_user_id=remover_id,
            room_title=room.title
        )
        
        return {"message": "Member removed successfully"}
    
    async def update_group_info(
        self,
        db: Session,
        room_id: UUID,
        updater_id: UUID,
        update_data: GroupUpdateRequest,
        avatar: Optional[UploadFile] = None
    ):
        """Update group information (title, description, avatar)"""

        # --- Get room (KHÔNG lấy room đã bị delete) ---
        room = db.query(ChatRoom).filter(
            ChatRoom.id == room_id,
            ChatRoom.is_active.is_(True),
            ChatRoom.deleted_at.is_(None)
        ).first()

        if not room:
            raise HTTPException(status_code=404, detail="Group not found")

        # --- Check admin ---
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == updater_id
        ).first()

        if not member or member.role != MemberRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only admins can update group info")

        changed_fields = []

        # --- Update title ---
        if update_data.title is not None:
            room.title = update_data.title
            changed_fields.append("title")

        # --- Update description ---
        if update_data.description is not None:
            room.description = update_data.description
            changed_fields.append("description")

        # --- Upload avatar giống create ---
        if avatar:
            upload_result = await upload_and_save_metadata(
                db=db,
                uploaded_file=avatar,
                user_id=updater_id,
                folder="group_avatars"
            )
            room.avatar_url = upload_result.file_path
            changed_fields.append("avatar")

        db.commit()
        db.refresh(room)

        # --- Notify members ---
        if changed_fields:
            await manager.notify_group_updated(
                room_id=room_id,
                updated_by_user_id=updater_id,
                updates={
                    "changed_fields": changed_fields,
                    "title": room.title,
                    "description": room.description,
                    "avatar_url": room.avatar_url
                }
            )

        return room

    
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
        db.commit()

        return {
            "success": True,
            "room_id": str(room_id),
            "message": "Chat room deleted successfully"
        }
    
    async def get_group_members(self, db: Session, room_id: UUID, user_id: UUID):
        """Get all members of a group with their details"""
        # Check if user is member
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == user_id
        ).first()
        
        if not member:
            raise HTTPException(status_code=403, detail="Not a member of this group")
        
        # Get all members with user info
        members = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id
        ).all()
        
        result = []
        for m in members:
            user = self.user_repo.get(db, id=m.user_id)
            is_online = await manager.is_user_online(m.user_id)
            result.append({
                'user_id': str(m.user_id),
                'full_name': (user.first_name + " " + user.last_name) if user else "Unknown",
                'avatar_url': getattr(user, 'avatar_url', None) if user else None,
                'role': m.role.value,
                'joined_at': m.joined_at,
                'nickname': m.nickname,
                'email': getattr(user, 'email', None) if user else None,
                'is_online': is_online
            })
        
        return result
    
    async def _send_system_message(self, db: Session, room_id: UUID, content: str):
        """Send system message to group"""
        system_msg = Message(
            chat_room_id=room_id,
            sender_id=None,  # System message
            message_type=MessageType.SYSTEM,
            content=content,
            status=MessageStatus.SENT
        )
        db.add(system_msg)
        db.commit()
        db.refresh(system_msg)
        
        # Broadcast to all online members
        await manager.broadcast_to_room(
            room_id=room_id,
            message={
                'type': 'system_message',
                'message_id': str(system_msg.id),
                'room_id': str(room_id),
                'content': content,
                'timestamp': system_msg.created_at.isoformat()
            },
            db_session=db
        )

    def get_total_unread_count(self, db: Session, user_id: UUID):
        """Get total unread message count across all conversations for a user"""
        total_unread = db.query(func.count(MessageRecipient.id)).join(
            Message, Message.id == MessageRecipient.message_id
        ).filter(
            MessageRecipient.recipient_id == user_id,
            MessageRecipient.read_at.is_(None)
        ).scalar()
        
        return total_unread

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

message_service = MessageService()