from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class ChatbotDocumentResponse(BaseModel):
    id: UUID
    doc_id: Optional[str] = None
    filename: str
    category: str
    status: str = "completed"
    error_message: Optional[str] = None
    uploaded_by_name: str = ""
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
