from sqlalchemy import Column, DateTime, UUID, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import uuid

Base = declarative_base()

class AuditMixin:
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)
    created_by = Column(UUID, ForeignKey("users.id"), nullable=True) 
    updated_by = Column(UUID, ForeignKey("users.id"), nullable=True)

class BaseModel(Base, AuditMixin):
    __abstract__ = True
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)