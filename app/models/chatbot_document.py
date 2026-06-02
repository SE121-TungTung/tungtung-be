from sqlalchemy import Column, String, Enum
from app.models.base import BaseModel
import enum

class DocCategory(str, enum.Enum):
    business = "business"
    learning = "learning"

class ChatbotDocument(BaseModel):
    __tablename__ = "chatbot_documents"

    doc_id = Column(String(36), unique=True, index=True, nullable=False)
    filename = Column(String(255), nullable=False)
    category = Column(Enum(DocCategory), default=DocCategory.business, nullable=False)
