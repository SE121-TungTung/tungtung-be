from sqlalchemy import Column, String, Enum, Text, Boolean, JSON
from app.models.base import BaseModel
import enum

DEFAULT_DOCUMENT_AUDIENCE = ["student", "teacher", "staff", "admin"]


class DocCategory(str, enum.Enum):
    business = "business"
    learning = "learning"


class DocStatus(str, enum.Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ChatbotDocument(BaseModel):
    __tablename__ = "chatbot_documents"

    doc_id = Column(String(36), unique=True, index=True, nullable=True)
    filename = Column(String(255), nullable=False)
    category = Column(Enum(DocCategory), default=DocCategory.business, nullable=False)
    audience = Column(JSON, default=lambda: list(DEFAULT_DOCUMENT_AUDIENCE), nullable=False)
    audience_reviewed = Column(Boolean, default=False, nullable=False)
    status = Column(Enum(DocStatus), default=DocStatus.processing, nullable=False)
    error_message = Column(Text, nullable=True)
