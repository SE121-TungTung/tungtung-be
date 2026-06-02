from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class ChatbotDocumentResponse(BaseModel):
    id: UUID
    doc_id: str
    filename: str
    category: str
    uploaded_by_name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
