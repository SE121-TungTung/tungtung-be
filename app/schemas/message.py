from pydantic import BaseModel, ConfigDict, Field
from uuid import UUID
from typing import Optional, List, Any
from datetime import datetime

# ============================================================
# 1. REQUEST SCHEMAS (Giữ nguyên của bạn - Frontend gửi lên)
# ============================================================

class MessageCreate(BaseModel):
    room_id: Optional[UUID] = None
    receiver_id: Optional[UUID] = None
    content: str = Field(..., min_length=1)
    # attachment_ids: Optional[List[UUID]] = Field(default_factory=list)

class GroupCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    member_ids: List[UUID] = Field(..., min_items=1)  # At least 1 member

class GroupUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None

class AddMembersRequest(BaseModel):
    user_ids: List[UUID] = Field(..., min_items=1)

# ============================================================
# 2. RESPONSE SCHEMAS (Chuẩn hóa Pydantic V2 - Trả về Frontend)
# ============================================================

class LastMessageResponse(BaseModel):
    message_id: Optional[UUID] = None
    content: Optional[str] = None
    timestamp: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ConversationResponse(BaseModel):
    """Schema danh sách hội thoại (Sát với UI)"""
    room_id: UUID = Field(alias="id") # Map trường id của DB sang room_id cho Frontend
    room_type: str
    title: Optional[str] = None
    other_user_id: Optional[UUID] = None
    
    last_message: Optional[LastMessageResponse] = None
    last_message_at: Optional[datetime] = None
    
    unread_count: int = 0
    avatar_url: Optional[str] = None
    description: Optional[str] = None
    member_count: int = 0
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class MemberResponse(BaseModel):
    """Schema thành viên trong nhóm"""
    user_id: UUID
    role: str
    joined_at: Optional[datetime] = None
    nickname: Optional[str] = None
    
    # Các trường join từ bảng User
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    email: Optional[str] = None
    is_online: Optional[bool] = None
    
    model_config = ConfigDict(from_attributes=True)

class GroupDetailResponse(BaseModel):
    """Schema chi tiết một nhóm chat"""
    id: UUID
    title: Optional[str] = None
    description: Optional[str] = None
    avatar_url: Optional[str] = None
    room_type: str
    created_at: Optional[datetime] = None
    
    member_count: int = 0
    members: List[MemberResponse] = Field(default_factory=list)
    
    model_config = ConfigDict(from_attributes=True)

# ============================================================
# 3. NEW RESPONSE SCHEMAS (Bổ sung cho các API bị thiếu)
# ============================================================

class MessageResponse(BaseModel):
    """Schema chi tiết của 1 tin nhắn (Dùng cho Lịch sử chat và Gửi tin nhắn)"""
    id: UUID
    sender_id: Optional[UUID] = None
    chat_room_id: Optional[UUID] = None
    sender: Optional[Any] = None  # UserMiniResponse khi có sender

    message_type: str
    content: str
    attachments: List[Any] = Field(default_factory=list)

    priority: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    # UI helper flags
    is_read: bool = False
    is_starred: bool = False
    is_edited: bool = False

    model_config = ConfigDict(from_attributes=True)

class UnreadCountResponse(BaseModel):
    """Schema cho API đếm tổng tin chưa đọc"""
    unread_count: int

class MessageEditRequest(BaseModel):
    new_content: str = Field(..., min_length=1)