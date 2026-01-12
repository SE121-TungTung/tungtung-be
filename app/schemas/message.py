from pydantic import BaseModel
from uuid import UUID
from typing import Optional
from datetime import datetime
from typing import List
from pydantic import Field

class MessageCreate(BaseModel):
    room_id: Optional[UUID] = None
    receiver_id: Optional[UUID] = None
    
    content: str = Field(..., min_length=1)
    # attachment_ids: Optional[List[UUID]] = Field(default_factory=list)

class LastMessageResponse(BaseModel):
    message_id: Optional[UUID]
    content: Optional[str]
    timestamp: Optional[datetime]

class ConversationResponse(BaseModel):
    room_id: UUID
    room_type: str
    title: str
    other_user_id: Optional[UUID]
    last_message: Optional[LastMessageResponse]
    last_message_at: Optional[datetime]
    unread_count: int
    avatar_url: Optional[str]
    description: Optional[str] = None
    member_count: int = 0
    

#  Group Chat Schemas
class GroupCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    member_ids: List[UUID] = Field(..., min_items=1)  # At least 1 member

class GroupUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None

class AddMembersRequest(BaseModel):
    user_ids: List[UUID] = Field(..., min_items=1)

class MemberResponse(BaseModel):
    user_id: UUID
    role: str
    joined_at: Optional[datetime] = None
    nickname: Optional[str]
    full_name: Optional[str]
    avatar_url: Optional[str]
    email: Optional[str] = None
    is_online: Optional[bool] = None
    
    class Config:
        from_attributes = True

class GroupDetailResponse(BaseModel):
    id: UUID
    title: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    room_type: str
    created_at: datetime
    member_count: int
    members: List[MemberResponse]
    
    class Config:
        from_attributes = True