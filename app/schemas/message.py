from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from datetime import datetime

class MessageCreate(BaseModel):
    receiver_id: UUID
    content: str

class LastMessageResponse(BaseModel):
    message_id: Optional[UUID]
    content: Optional[str]
    timestamp: Optional[datetime]


class ConversationResponse(BaseModel):
    room_id: UUID
    room_type: str
    title: str
    last_message: Optional[LastMessageResponse]