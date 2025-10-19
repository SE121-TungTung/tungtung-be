# TEMPORARY NOT USED
# 
#  from pydantic import BaseModel, Field, validator
# from typing import Optional, List, Dict, Any
# from datetime import datetime
# from app.models.academic import RoomType, RoomStatus
# import uuid

# class RoomBase(BaseModel):
#     name: str = Field(..., min_length=1, max_length=100)
#     capacity: int = Field(..., ge=5, le=50)
#     location: Optional[str] = None
#     equipment: Optional[List[Dict[str, Any]]] = []
#     room_type: RoomType = RoomType.CLASSROOM
#     status: RoomStatus = RoomStatus.AVAILABLE
#     notes: Optional[str] = None
    
#     @validator('name')
#     def validate_name(cls, v):
#         if not v.strip():
#             raise ValueError('Room name cannot be empty')
#         return v.strip()

# class RoomCreate(RoomBase):
#     pass

# class RoomUpdate(BaseModel):
#     name: Optional[str] = None
#     capacity: Optional[int] = Field(None, ge=5, le=50)
#     location: Optional[str] = None
#     equipment: Optional[List[Dict[str, Any]]] = None
#     room_type: Optional[RoomType] = None
#     status: Optional[RoomStatus] = None
#     notes: Optional[str] = None

# class RoomResponse(RoomBase):
#     id: uuid.UUID
#     created_at: datetime
#     updated_at: datetime
    
#     class Config:
#         from_attributes = True

# class RoomListResponse(BaseModel):
#     items: List[RoomResponse]
#     total: int
#     page: int
#     size: int
#     pages: int