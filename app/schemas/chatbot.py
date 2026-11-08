from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from uuid import UUID


class ChatbotDocumentAudienceUpdate(BaseModel):
    audience: List[str] = Field(
        ...,
        description="Danh sách đối tượng được phép truy xuất: public, student, teacher, staff, admin",
    )
    audience_reviewed: bool = Field(True, description="Đánh dấu đã rà soát quyền truy cập")


class ChatbotDocumentBulkAudienceUpdate(BaseModel):
    document_ids: List[str] = Field(..., description="Danh sách ID tài liệu cần cập nhật")
    audience: List[str] = Field(..., description="Danh sách đối tượng được phép truy xuất")
    audience_reviewed: bool = Field(True, description="Đánh dấu đã rà soát quyền truy cập")


class ChatbotDocumentResponse(BaseModel):
    id: UUID
    doc_id: Optional[str] = None
    filename: str
    category: str
    audience: List[str] = ["student", "teacher", "staff", "admin"]
    audience_reviewed: bool = False
    status: str = "completed"
    error_message: Optional[str] = None
    uploaded_by_name: str = ""
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
