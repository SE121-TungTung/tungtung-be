from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from app.models.class_post import ClassPostType

class ClassPostBase(BaseModel):
    title: str
    content: Optional[str] = None
    post_type: ClassPostType = ClassPostType.ANNOUNCEMENT
    attachments: Optional[List[Dict[str, Any]]] = []

class ClassPostCreate(ClassPostBase):
    class_id: UUID

class ClassPostUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None

class ClassPostAuthorResponse(BaseModel):
    id: UUID
    full_name: str
    role: str
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True

class ClassPostResponse(ClassPostBase):
    id: UUID
    class_id: UUID
    author_id: UUID
    author: Optional[ClassPostAuthorResponse] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
