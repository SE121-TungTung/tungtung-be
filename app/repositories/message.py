from app.routers.generic_crud import CRUDBase
from app.models.message import Message, MessageRecipient, ChatRoom
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Dict

class MessageRepository(CRUDBase):
    def __init__(self):
        super().__init__(Message)

class MessageRecipientRepository(CRUDBase):
    def __init__(self):
        super().__init__(MessageRecipient)
    
    def get_statuses_for_user(self, db: Session, user_id: UUID, message_ids: List[UUID]) -> Dict:
        statuses = db.query(MessageRecipient).filter(
            MessageRecipient.recipient_id == user_id,
            MessageRecipient.message_id.in_(message_ids)
        ).all()
        
        return {
            status.message_id: {
                'read_at': status.read_at,
                'starred': status.starred,
                'deleted': status.deleted,
                'archived': status.archived
            }
            for status in statuses
        }
    
    def count_unread(self, db: Session, user_id: UUID, room_id: UUID) -> int:
        return db.query(MessageRecipient).filter(
            MessageRecipient.recipient_id == user_id,
            MessageRecipient.message.has(Message.chat_room_id == room_id),
            MessageRecipient.read_at.is_(None)
        ).count()

class ChatRoomRepository(CRUDBase):
    def __init__(self):
        super().__init__(ChatRoom)

message_repository = MessageRepository()
recipient_repository = MessageRecipientRepository()
chat_room_repository = ChatRoomRepository()