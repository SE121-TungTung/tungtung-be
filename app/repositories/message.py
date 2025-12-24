from app.routers.generic_crud import CRUDBase
from app.models.message import Message, MessageRecipient, ChatRoom
from sqlalchemy.orm import Session
from sqlalchemy import func
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
    
    def mark_room_as_read(self, db: Session, user_id: UUID, room_id: UUID) -> int:
        """
        Đánh dấu tất cả tin nhắn trong một phòng là đã đọc cho user cụ thể.
        Logic: 
        Update bảng MessageRecipient
        Set read_at = NOW()
        Where recipient_id = user_id
          AND read_at IS NULL (chưa đọc)
          AND message_id thuộc về room_id
        """
        # Subquery: Lấy danh sách ID các tin nhắn thuộc phòng này
        message_ids_subquery = db.query(Message.id).filter(
            Message.chat_room_id == room_id
        )
        
        # Thực hiện update
        result = db.query(self.model).filter(
            self.model.recipient_id == user_id,
            self.model.read_at.is_(None),  # Chỉ update cái chưa đọc
            self.model.message_id.in_(message_ids_subquery)
        ).update(
            {self.model.read_at: func.now()},
            synchronize_session=False
        )
        
        db.commit()
        return result

class ChatRoomRepository(CRUDBase):
    def __init__(self):
        super().__init__(ChatRoom)

message_repository = MessageRepository()
recipient_repository = MessageRecipientRepository()
chat_room_repository = ChatRoomRepository()