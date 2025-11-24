from app.repositories.message import (
    message_repository, 
    recipient_repository, 
    chat_room_repository
)
from app.repositories.user import user_repository
from app.services.websocket import manager
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Dict, Any, List
from app.schemas.message import MessageCreate
from app.models.message import Message
from app.schemas.message import ConversationResponse


class MessageService:
    def __init__(self):
        self.message_repo = message_repository
        self.recipient_repo = recipient_repository
        self.chat_room_repo = chat_room_repository
        self.user_repo = user_repository
    
    def _get_or_create_direct_room(self, db: Session, sender_id: UUID, receiver_id: UUID):
        """Get or create 1-1 chat room"""
        from app.models.message import ChatRoom, MessageType
        
        ids = sorted([str(sender_id), str(receiver_id)])
        p1_id, p2_id = UUID(ids[0]), UUID(ids[1])
        
        room = db.query(ChatRoom).filter(
            ChatRoom.room_type == MessageType.DIRECT.value,
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
        message_data: MessageCreate
    ):
        """Handle new message with WebSocket"""
        receiver_id = message_data.receiver_id
        content = message_data.content
        
        if not receiver_id or not content:
            raise ValueError("Missing receiver_id or content")
        
        room = self._get_or_create_direct_room(db, sender_id, receiver_id)
        
        # Save message
        message_db_data = {
            "sender_id": sender_id,
            "chat_room_id": room.id,
            "content": content,
            "message_type": "direct",
            "status": "sent"
        }
        new_message = self.message_repo.create(db, obj_in=message_db_data)
        
        # Create recipient records
        for recipient_id in [sender_id, receiver_id]:
            recipient_data = {
                "message_id": new_message.id,
                "recipient_id": recipient_id,
                "recipient_type": "user"
            }
            self.recipient_repo.create(db, obj_in=recipient_data)
        
        db.commit()
        db.refresh(new_message)
        
        # Send via WebSocket
        payload = {
            "type": "new_message",
            "message_id": str(new_message.id),
            "sender_id": str(sender_id),
            "content": content,
            "timestamp": str(new_message.created_at)
        }
        
        await manager.send_personal_message(payload, receiver_id)
        await manager.send_personal_message(payload, sender_id)
        
        return new_message
    
    async def get_user_conversations(
        self, 
        db: Session, 
        user_id: UUID
    ) -> List[Dict[str, Any]]:
        """Get list of conversations for a user"""
        from app.models.message import ChatRoom, Message
        
        rooms = db.query(ChatRoom).filter(
            ((ChatRoom.participant1_id == user_id) | (ChatRoom.participant2_id == user_id))
        ).all()
        
        conversations = []
        for room in rooms:
            last_message = db.query(Message).filter(
                Message.chat_room_id == room.id
            ).order_by(Message.created_at.desc()).first()
            
            conversations.append(ConversationResponse(
                room_id=room.id,
                room_type=room.room_type,
                title=room.title,
                last_message={
                    "message_id": last_message.id if last_message else None,
                    "content": last_message.content if last_message else None,
                    "timestamp": last_message.created_at if last_message else None
                } if last_message else None
            ))
        
        return conversations
    
    async def get_or_create_direct_conversation(
        self, 
        db: Session, 
        user_id: UUID, 
        other_user_id: UUID
    ) -> Dict[str, Any]:
        """Get or create a direct conversation between two users"""
        room = self._get_or_create_direct_room(db, user_id, other_user_id)
        
        last_message = db.query(Message).filter(
            Message.chat_room_id == room.id
        ).order_by(Message.created_at.desc()).first()
        
        return {
            "room_id": str(room.id),
            "room_type": room.room_type,
            "title": room.title,
            "last_message": {
                "message_id": str(last_message.id) if last_message else None,
                "content": last_message.content if last_message else None,
                "timestamp": str(last_message.created_at) if last_message else None
            }
        }
    
    async def get_chat_history(
        self, 
        db: Session, 
        room_id: UUID, 
        current_user_id: UUID, 
        skip: int = 0, 
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get chat history with sparse status"""
        from app.models.message import Message
        
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
            
            history.append({
                "message_id": str(msg.id),
                "sender_id": str(msg.sender_id),
                "content": msg.content,
                "timestamp": str(msg.created_at),
                "is_read": status.get('read_at') is not None,
                "is_starred": status.get('starred', False)
            })
        
        return history

message_service = MessageService()