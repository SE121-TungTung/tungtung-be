from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from app.models.user import UserRole, UserStatus
import uuid

# Base schemas
class UserBase(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, pattern=r'^\+?[0-9\s\-\(\)]{10,15}$')
    date_of_birth: Optional[date] = None
    address: Optional[str] = None

class UserCreate(UserBase):
    role: UserRole = UserRole.STUDENT
    
class UserBulkCreate(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    role: UserRole = UserRole.STUDENT
    class_id: Optional[uuid.UUID] = None

class BulkImportRequest(BaseModel):
    """Schema đại diện cho toàn bộ request Bulk Import."""
    users: List[UserBulkCreate] # Đây là danh sách các users cần tạo

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None

class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)
    
    @field_validator('new_password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

class UserResponse(UserBase):
    id: uuid.UUID
    role: UserRole
    status: UserStatus
    avatar_url: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {
        "from_attributes": True,
        "json_encoders": {
            uuid.UUID: str   # ép UUID về string khi trả JSON
        }
    }

class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
    page: int
    size: int
    pages: int

    model_config = {
        "from_attributes": True
    }