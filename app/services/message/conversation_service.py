from uuid import UUID
from typing import List, Dict, Any
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from app.models.message import Message, ChatRoom, ChatRoomMember, MessageType
from app.models.user import User
from app.schemas.message import ConversationResponse

class ConversationService:
    async def get_user_conversations(
        self,
        db: Session,
        user_id: UUID
    ) -> List[ConversationResponse]:
        """
        Get all conversations of user (DIRECT + GROUP + CLASS)

        Rules:
        - GROUP/CLASS: show only if ChatRoomMember exists (hard delete)
        - DIRECT: hide if user cleared chat (last_read_at),
                show again only when new message arrives
        """

        from sqlalchemy import func, or_, and_
        from sqlalchemy.orm import aliased
        from app.models.message import MessageRecipient

        # ======================================================
        # 1. Last message per room (Postgres DISTINCT ON)
        # ======================================================
        last_msg_sub = (
            db.query(
                Message.chat_room_id,
                Message.id.label("last_msg_id"),
                Message.content.label("last_msg_content"),
                Message.sender_id.label("last_msg_sender"),
                Message.created_at.label("last_msg_time"),
            )
            .distinct(Message.chat_room_id)
            .order_by(
                Message.chat_room_id,
                Message.created_at.desc(),
            )
            .subquery()
        )

        # ======================================================
        # 2. Unread count per room
        # ======================================================
        unread_sub = (
            db.query(
                Message.chat_room_id,
                func.count(MessageRecipient.id).label("unread_count"),
            )
            .join(MessageRecipient, Message.id == MessageRecipient.message_id)
            .filter(
                MessageRecipient.recipient_id == user_id,
                MessageRecipient.read_at.is_(None),
            )
            .group_by(Message.chat_room_id)
            .subquery()
        )

        # ======================================================
        # 3. Member count (GROUP / CLASS)
        # ======================================================
        member_count_sub = (
            db.query(
                ChatRoomMember.chat_room_id,
                func.count(ChatRoomMember.user_id).label("member_count"),
            )
            .group_by(ChatRoomMember.chat_room_id)
            .subquery()
        )

        # ======================================================
        # 4. Alias
        # ======================================================
        User1 = aliased(User, name="u1")
        User2 = aliased(User, name="u2")

        # Alias member riêng cho user hiện tại
        CRM = aliased(ChatRoomMember)

        # ======================================================
        # 5. MAIN QUERY
        # ======================================================
        rows = (
            db.query(
                ChatRoom,
                last_msg_sub.c.last_msg_id,
                last_msg_sub.c.last_msg_content,
                last_msg_sub.c.last_msg_sender,
                last_msg_sub.c.last_msg_time,
                func.coalesce(unread_sub.c.unread_count, 0).label("unread_count"),
                func.coalesce(member_count_sub.c.member_count, 0).label("member_count"),
                User1,
                User2,
                CRM.last_read_at.label("member_last_read_at"),
            )
            .outerjoin(last_msg_sub, ChatRoom.id == last_msg_sub.c.chat_room_id)
            .outerjoin(unread_sub, ChatRoom.id == unread_sub.c.chat_room_id)
            .outerjoin(member_count_sub, ChatRoom.id == member_count_sub.c.chat_room_id)
            .outerjoin(User1, ChatRoom.participant1_id == User1.id)
            .outerjoin(User2, ChatRoom.participant2_id == User2.id)
            .outerjoin(
                CRM,
                and_(
                    CRM.chat_room_id == ChatRoom.id,
                    CRM.user_id == user_id,
                ),
            )
            .filter(
                ChatRoom.deleted_at.is_(None),
                ChatRoom.is_active.is_(True),
                or_(
                    # ==========================
                    # DIRECT
                    # ==========================
                    and_(
                        ChatRoom.room_type == MessageType.DIRECT,
                        or_(
                            ChatRoom.participant1_id == user_id,
                            ChatRoom.participant2_id == user_id,
                        ),
                        or_(
                            CRM.id.is_(None),
                            last_msg_sub.c.last_msg_time > CRM.last_read_at,
                        ),
                    ),
                    # ==========================
                    # GROUP / CLASS
                    # ==========================
                    and_(
                        ChatRoom.room_type != MessageType.DIRECT,
                        CRM.id.isnot(None),
                    ),
                ),
            )
            .order_by(
                ChatRoom.last_message_at.desc().nulls_last(),
                ChatRoom.created_at.desc(),
            )
            .all()
        )

        # ======================================================
        # 6. MAP RESULT → RESPONSE
        # ======================================================
        conversations: list[ConversationResponse] = []

        for row in rows:
            room = row.ChatRoom

            title = room.title if room.title else "Chat room"
            avatar_url = room.avatar_url
            description = room.description
            member_count = row.member_count

            # ---------- DIRECT ----------
            if room.room_type == MessageType.DIRECT:
                other_user = row.u2 if room.participant1_id == user_id else row.u1
                other_user_id = None
                if other_user:
                    title = f"{other_user.first_name} {other_user.last_name}"
                    avatar_url = other_user.avatar_url
                    description = None
                    other_user_id = other_user.id
                else:
                    title = "Unknown user"
                    avatar_url = None

                member_count = 2

            # ---------- LAST MESSAGE ----------
            last_message = None
            if row.last_msg_id:
                last_message = {
                    "message_id": str(row.last_msg_id),
                    "content": row.last_msg_content,
                    "sender_id": str(row.last_msg_sender),
                    "timestamp": row.last_msg_time,
                }

            conversations.append(
                ConversationResponse(
                    room_id=room.id,
                    room_type=room.room_type.value,
                    title=title or "No title",
                    other_user_id=other_user_id if room.room_type == MessageType.DIRECT else None,
                    avatar_url=avatar_url,
                    description=description,
                    member_count=member_count,
                    last_message=last_message,
                    last_message_at=room.last_message_at,
                    unread_count=row.unread_count,
                )
            )

        return conversations

    
    async def get_or_create_direct_conversation(
        self,
        db: Session,
        user_id: UUID,
        other_user_id: UUID
    ) -> Dict[str, Any]:
        """Get or create a direct conversation between two users"""

        # 1. Normalize & sort user ids (giữ nguyên ý tưởng ban đầu, bỏ ép kiểu thừa)
        participant_ids = sorted([user_id, other_user_id], key=lambda x: str(x))

        # 2. Try to get existing DIRECT room
        room = db.query(ChatRoom).filter(
            ChatRoom.room_type == MessageType.DIRECT,
            ChatRoom.participant1_id == participant_ids[0],
            ChatRoom.participant2_id == participant_ids[1],
            ChatRoom.deleted_at.is_(None),
            ChatRoom.is_active.is_(True)
        ).first()

        # 3. CREATE room nếu chưa tồn tại (đúng nghĩa get_or_create)
        if room is None:
            room = ChatRoom(
                room_type=MessageType.DIRECT,
                participant1_id=participant_ids[0],
                participant2_id=participant_ids[1],
                is_active=True
            )
            db.add(room)
            db.commit()
            db.refresh(room)

        # 4. Get other user info (có guard)
        other_user = self.user_repo.get(db, id=other_user_id)

        # 5. Get last message (CHỈ khi room đã chắc chắn tồn tại)
        last_message = db.query(Message).filter(
            Message.chat_room_id == room.id
        ).order_by(Message.created_at.desc()).first()

        # 6. Build response (không crash nếu thiếu user / message)
        return {
            "room_id": str(room.id),
            "room_type": room.room_type.value,
            "title": (
                f"{other_user.first_name} {other_user.last_name}"
                if other_user else "Unknown User"
            ),
            "avatar_url": getattr(other_user, "avatar_url", None) if other_user else None,
            "last_message": {
                "message_id": str(last_message.id),
                "content": last_message.content,
                "timestamp": last_message.created_at.isoformat()
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
                "is_starred": status.get("starred", False),
                "is_edited": msg.updated_at != msg.created_at
            })

        history.reverse()
        return history
    
message_conversation_service = ConversationService()