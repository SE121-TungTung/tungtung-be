from uuid import UUID
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile
from app.models.message import ChatRoom, ChatRoomMember, Message, MessageType, MemberRole, MessageStatus, MessagePriority
from app.models.user import User
from app.models.audit_log import AuditAction
from app.schemas.message import GroupCreateRequest, GroupUpdateRequest, GroupDetailResponse, MemberResponse
from app.services.cloudinary import upload_and_save_metadata
from app.services.audit_log_service import audit_service
import logging

logger = logging.getLogger(__name__)

class GroupService:
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
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    raise HTTPException(
                        status_code=404, 
                        detail=f"User {user_id} not found"
                    )
            avatar_url = None
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
        
            creator = db.query(User).filter(User.id == creator_id).first()
            creator_name = (creator.first_name + " " + creator.last_name) if creator else "Someone"
            # Send system message
            await self._send_system_message(
                db, 
                chat_room.id, 
                f"Group '{chat_room.title}' was created by {creator_name}"
            )
                        
            audit_service.log(
                db=db,
                action=AuditAction.CREATE,
                table_name="chat_rooms",
                record_id=chat_room.id,
                user_id=creator_id,
                new_values={
                    "room_type": "GROUP",
                    "title": chat_room.title,
                    "members": [str(uid) for uid in member_ids]
                }
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
        from app.services.websocket import websocket_manager as manager

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
            user = db.query(User).filter(User.id == user_id).first()
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
        user_id_to_remove: UUID,
        new_admin_id: Optional[UUID] = None
    ):
        """
        Remove a member from group.
        If Admin leaves, they MUST provide `new_admin_id` if they are the last admin.
        """
        from app.services.websocket import websocket_manager as manager

        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Group not found")
        
        remover_member = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == remover_id
        ).first()
        
        is_admin = remover_member and remover_member.role == MemberRole.ADMIN
        is_self_leave = remover_id == user_id_to_remove
        
        if not (is_admin or is_self_leave):
            raise HTTPException(403, "Only admins can remove members, or you can leave yourself")
        
        member_to_remove = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == user_id_to_remove
        ).first()
        
        if not member_to_remove:
            raise HTTPException(404, "Member not found")
        
        if member_to_remove.role == MemberRole.ADMIN:
            remaining_admin_count = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room_id,
                ChatRoomMember.role == MemberRole.ADMIN,
                ChatRoomMember.user_id != user_id_to_remove
            ).count()
            
            if remaining_admin_count == 0:
                if not new_admin_id:
                     raise HTTPException(
                        status_code=400, 
                        detail="You are the last Admin. Please assign a new Admin before leaving."
                    )
                
                new_admin_member = db.query(ChatRoomMember).filter(
                    ChatRoomMember.chat_room_id == room_id,
                    ChatRoomMember.user_id == new_admin_id
                ).first()
                
                if not new_admin_member:
                    raise HTTPException(404, "New admin candidate is not in this group")
                
                new_admin_member.role = MemberRole.ADMIN
                db.add(new_admin_member)

                new_admin_name = f"{new_admin_member.user.first_name} {new_admin_member.user.last_name}" if new_admin_member.user else "Someone"

                await self._send_system_message(
                    db, room_id, 
                    f"Admin rights transferred to user {new_admin_name}"
                )

        db.delete(member_to_remove)
        db.commit()
        
        deleted_user = db.query(User).filter(User.id == user_id_to_remove).first()
        deleted_user_name = (deleted_user.first_name + " " + deleted_user.last_name) if deleted_user else "Someone"
        
        action = "left" if is_self_leave else "was removed from"
        await self._send_system_message(
            db,
            room_id,
            f"{deleted_user_name} {action} the group"
        )
        
        await manager.notify_member_removed(
            room_id=room_id,
            removed_user_id=user_id_to_remove,
            remover_id=remover_id,
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
        from app.services.websocket import websocket_manager as manager

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
                },
                db_session=db
            )

            audit_service.log(
                db=db,
                action=AuditAction.UPDATE,
                table_name="chat_rooms",
                record_id=room.id,
                user_id=updater_id,
                old_values={"changed_fields": changed_fields},
                new_values={
                    "title": room.title,
                    "description": room.description,
                    "avatar_url": room.avatar_url
                }
            )

        db.commit()
        db.refresh(room)

        return room
    
    async def get_group_members(
        self,
        db: Session,
        room_id: UUID,
        user_id: UUID
    ):
        """Get all members of a chat room (DIRECT or GROUP)"""
        from app.services.websocket import websocket_manager as manager

        # 1️⃣ Validate room
        room = db.query(ChatRoom).filter(
            ChatRoom.id == room_id,
            ChatRoom.deleted_at.is_(None),
            ChatRoom.is_active.is_(True)
        ).first()

        if not room:
            raise HTTPException(status_code=404, detail="Group not found")

        if room.room_type == MessageType.DIRECT:
            other_user_id = (
                room.participant2_id
                if room.participant1_id == user_id
                else room.participant1_id
            )

            other_user = db.query(User).filter(User.id == other_user_id).first()
            if not other_user:
                return []

            is_online = await manager.is_user_online(other_user_id)

            return [{
                "user_id": str(other_user.id),
                "full_name": f"{other_user.first_name} {other_user.last_name}",
                "avatar_url": getattr(other_user, "avatar_url", None),
                "role": "participant",
                "joined_at": None,
                "nickname": None,
                "email": getattr(other_user, "email", None),
                "is_online": is_online
            }]

        member = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id,
            ChatRoomMember.user_id == user_id
        ).first()

        if not member:
            raise HTTPException(status_code=403, detail="Not a member of this group")

        members = db.query(ChatRoomMember).filter(
            ChatRoomMember.chat_room_id == room_id
        ).all()

        result = []

        for m in members:
            user = db.query(User).filter(User.id == m.user_id).first()
            is_online = await manager.is_user_online(m.user_id)

            result.append({
                "user_id": str(m.user_id),
                "full_name": (
                    f"{user.first_name} {user.last_name}"
                    if user else "Unknown"
                ),
                "avatar_url": getattr(user, "avatar_url", None) if user else None,
                "role": m.role.value,
                "joined_at": m.joined_at,
                "nickname": m.nickname,
                "email": getattr(user, "email", None) if user else None,
                "is_online": is_online
            })

        return result
    
    async def get_group_details(
        self,
        db: Session,
        room_id: UUID,
        user_id: UUID
    ):
        """Get group details including members"""
        members_data = await message_group_service.get_group_members(db, room_id, user_id)
        
        # Get room info
        room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Group not found")
        
        return GroupDetailResponse(
            id=room.id,
            title=room.title,
            description=room.description,
            avatar_url=room.avatar_url,
            room_type=room.room_type.value,
            created_at=room.created_at,
            member_count=len(members_data),
            members=[MemberResponse(
                user_id=m['user_id'],
                role=m['role'],
                joined_at=m['joined_at'],
                nickname=m.get('nickname'),
                full_name=m.get('full_name'),
                avatar_url=m.get('avatar_url'),
                email=m.get('email'),
                is_online=m.get('is_online')
            ) for m in members_data]
        )

    async def _send_system_message(self, db: Session, room_id: UUID, content: str):
        """Create a system message in a chat room (no sender)."""
        system_msg = Message(
            chat_room_id=room_id,
            sender_id=None,
            message_type=MessageType.SYSTEM,
            content=content,
            status=MessageStatus.SENT,
            priority=MessagePriority.NORMAL,
        )
        db.add(system_msg)
        db.flush()
    
message_group_service = GroupService()