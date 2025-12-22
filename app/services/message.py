from app.repositories.message import (
    message_repository, 
    recipient_repository, 
    chat_room_repository
)
from app.repositories.user import user_repository
from app.services.websocket import manager
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, Any, List, Optional
from app.schemas.message import MessageCreate, ConversationResponse, GroupCreateRequest
from app.models.message import Message, ChatRoom, ChatRoomMember, MessageType, MessageStatus, MemberRole
from fastapi import HTTPException
import logging
from app.schemas.notification import NotificationCreate
from app.models.notification import NotificationType, NotificationPriority
from app.services.notification import notification_service
from app.models.user import User
from datetime import datetime, timezone


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
        
        CRITICAL FIX:
        - Xử lý cả direct chat (với receiver_id) và group chat (với room_id)
        - Broadcast đúng cách cho từng loại chat
        """
        # Validate input
        room_id = getattr(message_data, 'room_id', None)
        receiver_id = getattr(message_data, 'receiver_id', None)
        content = message_data.content
        
        if not content:
            raise ValueError("Message content is required")
        
        # Determine chat type and get/create room
        if room_id:
            # GROUP/CLASS CHAT - Room already exists
            room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
            if not room:
                raise HTTPException(status_code=404, detail="Chat room not found")
            
            # Verify sender is a member of the room
            if room.room_type in [MessageType.GROUP, MessageType.CLASS]:
                member = db.query(ChatRoomMember).filter(
                    ChatRoomMember.chat_room_id == room_id,
                    ChatRoomMember.user_id == sender_id
                ).first()
                
                if not member:
                    raise HTTPException(status_code=403, detail="You are not a member of this chat")
        
        elif receiver_id:
            # DIRECT CHAT - Get or create room
            room = self._get_or_create_direct_room(db, sender_id, receiver_id)
        
        else:
            raise ValueError("Either room_id or receiver_id must be provided")
        
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
        
        # Create recipient records based on room type
        if room.room_type == MessageType.DIRECT:
            # Direct chat: sender + receiver
            for recipient_id in [sender_id, receiver_id]:
                recipient_data = {
                    "message_id": new_message.id,
                    "recipient_id": recipient_id,
                    "recipient_type": "user"
                }
                self.recipient_repo.create(db, obj_in=recipient_data)
        
        elif room.room_type in [MessageType.GROUP, MessageType.CLASS]:
            # Group/Class: all members
            members = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room.id
            ).all()
            
            for member in members:
                recipient_data = {
                    "message_id": new_message.id,
                    "recipient_id": member.user_id,
                    "recipient_type": "group" if room.room_type == MessageType.GROUP else "class"
                }
                self.recipient_repo.create(db, obj_in=recipient_data)
        
        members_to_notify = [] # List tạm để lưu những người cần nhận thông báo
        if room.room_type == MessageType.DIRECT:
            # Create recipient records
            for uid in [sender_id, receiver_id]:
                self.recipient_repo.create(db, obj_in={
                    "message_id": new_message.id, 
                    "recipient_id": uid, 
                    "recipient_type": "user"
                })
            
            # Chỉ định người nhận thông báo là receiver
            members_to_notify.append(receiver_id)

        elif room.room_type in [MessageType.GROUP, MessageType.CLASS]:
            members = db.query(ChatRoomMember).filter(ChatRoomMember.chat_room_id == room.id).all()
            for member in members:
                self.recipient_repo.create(db, obj_in={
                    "message_id": new_message.id, 
                    "recipient_id": member.user_id, 
                    "recipient_type": "group" if room.room_type == MessageType.GROUP else "class"
                })
                # Thêm vào list nhận thông báo (trừ người gửi)
                if str(member.user_id) != str(sender_id):
                    members_to_notify.append(member.user_id)

        # Update room's last_message_at
        room.last_message_at = new_message.created_at
        
        db.commit()
        db.refresh(new_message)
        
        # Prepare WebSocket payload
        payload = {
            "type": "new_message",
            "message_id": str(new_message.id),
            "sender_id": str(sender_id),
            "room_id": str(room.id),
            "room_type": room.room_type.value,
            "content": content,
            "timestamp": new_message.created_at.isoformat(),
            "attachments": new_message.attachments or []
        }
        
        # Send via WebSocket based on room type
        if room.room_type == MessageType.DIRECT:
            # Send to both sender and receiver
            await manager.send_to_user(receiver_id, payload)
            await manager.send_to_user(sender_id, payload)
        
        elif room.room_type in [MessageType.GROUP, MessageType.CLASS]:
            # Broadcast to all room members
            result = await manager.broadcast_to_room(
                room_id=room.id,
                message=payload,
                exclude_user=None,  # Send to everyone including sender
                db_session=db
            )
            logger.info(f"Broadcast result: {result}")
        
        if background_tasks:
        # Lấy thông tin người gửi để làm Title thông báo
            sender_user = db.query(User).filter(User.id == sender_id).first()
            sender_name = (sender_user.first_name + " " + sender_user.last_name) if sender_user else "Someone"
            
            # Nội dung rút gọn nếu quá dài
            preview_content = content[:100] + "..." if len(content) > 100 else content

            # Xác định Title và Action URL dựa trên loại phòng
            if room.room_type == MessageType.DIRECT:
                noti_title = f"{sender_name} đã gửi tin nhắn cho bạn"
                # Giả sử Frontend route là /messages/direct/{id}
                action_url = f"/messages/direct/{sender_id}" 
            else:
                # Nếu group có tên thì hiện tên group, không thì hiện chung chung
                group_name = getattr(room, 'name', 'Nhóm chat') or 'Nhóm chat'
                noti_title = f"{sender_name} nhắn trong {group_name}"
                action_url = f"/messages/group/{room.id}"

            # Loop qua danh sách cần gửi noti    (đã filter ở trên)
            for user_id_to_notify in members_to_notify:
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
                    channels=["in_app"] # Chat thường chỉ push in-app, tránh spam email
                )
                
                # Sử dụng background_tasks để không chặn process chính
                # Lưu ý: send_notification là hàm async, background_tasks.add_task hỗ trợ hàm async
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
        
        CRITICAL FIX:
        - Include group chats via ChatRoomMember
        - Sort by last_message_at
        - Include unread count
        """
        conversations = []
        
        # 1. Get DIRECT chats
        direct_rooms = db.query(ChatRoom).filter(
            ChatRoom.room_type == MessageType.DIRECT,
            ((ChatRoom.participant1_id == user_id) | (ChatRoom.participant2_id == user_id))
        ).all()
        
        for room in direct_rooms:
            # Get other participant info
            other_user_id = room.participant2_id if room.participant1_id == user_id else room.participant1_id
            other_user = self.user_repo.get(db, id=other_user_id)
            
            last_message = db.query(Message).filter(
                Message.chat_room_id == room.id
            ).order_by(Message.created_at.desc()).first()
            
            # Count unread messages
            unread_count = self.recipient_repo.count_unread(db, user_id, room.id)
            
            conversations.append(ConversationResponse(
                room_id=room.id,
                room_type=room.room_type.value,
                title=(other_user.first_name + " " + other_user.last_name) if other_user else "Unknown User",
                avatar_url=getattr(other_user, 'avatar_url', None) if other_user else None,
                last_message={
                    "message_id": str(last_message.id) if last_message else None,
                    "content": last_message.content if last_message else None,
                    "sender_id": str(last_message.sender_id) if last_message else None,
                    "timestamp": last_message.created_at.isoformat() if last_message else None
                } if last_message else None,
                last_message_at=room.last_message_at,
                unread_count=unread_count,
                member_count=2
            ))
        
        # 2. Get GROUP/CLASS chats via membership
        memberships = db.query(ChatRoomMember).filter(
            ChatRoomMember.user_id == user_id
        ).all()
        
        for membership in memberships:
            room = membership.chat_room
            
            last_message = db.query(Message).filter(
                Message.chat_room_id == room.id
            ).order_by(Message.created_at.desc()).first()
            
            # Count unread messages
            unread_count = self.recipient_repo.count_unread(db, user_id, room.id)
            
            # Count members
            member_count = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room.id
            ).count()
            
            conversations.append(ConversationResponse(
                room_id=room.id,
                room_type=room.room_type.value,
                title=room.title,
                avatar_url=room.avatar_url,
                description=room.description,
                last_message={
                    "message_id": str(last_message.id) if last_message else None,
                    "content": last_message.content if last_message else None,
                    "sender_id": str(last_message.sender_id) if last_message else None,
                    "timestamp": last_message.created_at.isoformat() if last_message else None
                } if last_message else None,
                last_message_at=room.last_message_at,
                unread_count=unread_count,
                member_count=member_count
            ))
        
        # Sort by last_message_at (most recent first)
        conversations.sort(
            key=lambda x: x.last_message_at or datetime.min.replace(tzinfo=timezone.utc), 
            reverse=True
        )
        
        return conversations
    
    async def get_or_create_direct_conversation(
        self, 
        db: Session, 
        user_id: UUID, 
        other_user_id: UUID
    ) -> Dict[str, Any]:
        """Get or create a direct conversation between two users"""
        room = self._get_or_create_direct_room(db, user_id, other_user_id)
        
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
        """
        Get chat history with sparse status
        
        CRITICAL FIX:
        - Verify user has access to room (either participant or member)
        - Include sender info
        """
        # Verify access
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        
        # Check if user has access
        has_access = False
        if room.room_type == MessageType.DIRECT:
            has_access = (room.participant1_id == current_user_id or 
                         room.participant2_id == current_user_id)
        else:
            member = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room_id,
                ChatRoomMember.user_id == current_user_id
            ).first()
            has_access = member is not None
        
        if not has_access:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get messages
        messages_db = db.query(Message).filter(
            Message.chat_room_id == room_id
        ).order_by(Message.created_at.desc()).offset(skip).limit(limit).all()
        
        if not messages_db:
            return []
        
        message_ids = [msg.id for msg in messages_db]
        sparse_statuses = self.recipient_repo.get_statuses_for_user(
            db, current_user_id, message_ids
        )
        
        history = []
        for msg in messages_db:
            status = sparse_statuses.get(msg.id, {})
            
            if status.get('deleted'):
                continue
            
            # Get sender info
            sender = self.user_repo.get(db, id=msg.sender_id) if msg.sender_id else None
            
            history.append({
                "message_id": str(msg.id),
                "sender_id": str(msg.sender_id) if msg.sender_id else None,
                "sender_name": (sender.first_name + " " + sender.last_name) if sender else "System",
                "content": msg.content,
                "message_type": msg.message_type.value,
                "timestamp": msg.created_at.isoformat(),
                "attachments": msg.attachments or [],
                "is_read": status.get('read_at') is not None,
                "is_starred": status.get('starred', False)
            })
        
        # Reverse to get chronological order (oldest first)
        history.reverse()
        
        return history
    
    # ========================
    # GROUP CHAT METHODS
    # ========================
    
    async def create_group_chat(
        self, 
        db: Session, 
        creator_id: UUID, 
        group_data: GroupCreateRequest
    ):
        """Create a new group chat"""
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
        
        # Create chat room
        chat_room = ChatRoom(
            room_type=MessageType.GROUP,
            title=group_data.title,
            description=group_data.description,
            avatar_url=group_data.avatar_url,
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
        
        db.commit()
        db.refresh(chat_room)
        
        creator = self.user_repo.get(db, id=creator_id)
        creator_name = (creator.first_name + " " + creator.last_name) if creator else "Someone"
        # Send system message
        await self._send_system_message(
            db, 
            chat_room.id, 
            f"Group '{chat_room.title}' was created by {creator_name}"
        )
        
        # Notify all members
        await manager.broadcast_to_room(
            room_id=chat_room.id,
            message={
                'type': 'group_created',
                'room_id': str(chat_room.id),
                'title': chat_room.title,
                'created_by': str(creator_id),
                'member_count': len(member_ids)
            },
            db_session=db
        )
        
        return chat_room
    
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
        updates: Dict[str, Any]
    ):
        """Update group information (title, description, avatar)"""
        # Get room
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Group not found")
        
        # Check if updater is admin
        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == updater_id
        ).first()
        
        if not member or member.role != MemberRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only admins can update group info")
        
        # Apply updates
        changed_fields = []
        if 'title' in updates and updates['title']:
            room.title = updates['title']
            changed_fields.append('title')
        
        if 'description' in updates:
            room.description = updates['description']
            changed_fields.append('description')
        
        if 'avatar_url' in updates:
            room.avatar_url = updates['avatar_url']
            changed_fields.append('avatar')
        
        db.commit()
        db.refresh(room)
        
        # Notify members
        if changed_fields:
            await manager.notify_group_updated(
                room_id=room_id,
                updated_by_user_id=updater_id,
                updates={'changed_fields': changed_fields, **updates}
            )
        
        return room
    
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
            result.append({
                'user_id': str(m.user_id),
                'full_name': (user.first_name + " " + user.last_name) if user else "Unknown",
                'avatar_url': getattr(user, 'avatar_url', None) if user else None,
                'role': m.role.value,
                'joined_at': m.joined_at,
                'nickname': m.nickname,
                'email': getattr(user, 'email', None) if user else None,
                'is_online': manager.is_user_online(m.user_id)
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


message_service = MessageService()