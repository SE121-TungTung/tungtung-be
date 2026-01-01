from sqlalchemy import (
    Column, String, Boolean, ForeignKey, Text, JSON, TIMESTAMP
)
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.sql import func
import uuid

import enum
from sqlalchemy.types import Enum
from app.models.base import BaseModel
from datetime import datetime

from typing import Optional, Dict, Any

class AuditAction(enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    PUBLISH = "PUBLISH"
    UNPUBLISH = "UNPUBLISH"
    SUBMIT = "SUBMIT"
    GRADE = "GRADE"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"

class AuditLog(BaseModel):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    action = Column(Enum(AuditAction, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='user_status'), nullable=False)

    table_name = Column(String(100), nullable=False)
    record_id = Column(UUID(as_uuid=True), nullable=True)

    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)

    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)
    session_id = Column(UUID(as_uuid=True), nullable=True)

    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now())

    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

# Schemas for AuditLog

class AuditLogCreate(BaseModel):
    user_id: Optional[UUID]
    action: str
    table_name: str
    record_id: Optional[UUID]
    old_values: Optional[Dict[str, Any]]
    new_values: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    user_agent: Optional[str]
    session_id: Optional[UUID]
    success: bool = True
    error_message: Optional[str]

    model_config = {
        "from_attributes": True
    }

class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID]
    action: str
    table_name: str
    record_id: Optional[UUID]

    old_values: Optional[Dict[str, Any]]
    new_values: Optional[Dict[str, Any]]

    ip_address: Optional[str]
    user_agent: Optional[str]
    session_id: Optional[UUID]

    success: bool
    error_message: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    total: int
    skip: int
    limit: int
    items: list[AuditLogResponse]