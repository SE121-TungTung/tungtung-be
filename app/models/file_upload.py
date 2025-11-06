import enum
from sqlalchemy import Column, String, BigInteger, Boolean, Integer, Text, ForeignKey, TIMESTAMP, func, CheckConstraint, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.models.base import Base

# ----------------------------------------------------------------------
# 1. ENUM Definitions
# ----------------------------------------------------------------------

class UploadType(enum.Enum):
    """Xác định mục đích sử dụng của file."""
    AVATAR = "avatar"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    IMAGE = "image"
    ASSIGNMENT = "assignment"
    RESOURCE = "resource"

class ProcessingStatus(enum.Enum):
    """Trạng thái xử lý hậu kỳ."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ScanStatus(enum.Enum):
    """Trạng thái quét virus/bảo mật."""
    PENDING = "pending"
    SCANNING = "scanning"
    CLEAN = "clean"
    INFECTED = "infected"
    FAILED = "failed"
    
class AccessLevel(enum.Enum):
    """Mức độ truy cập của file."""
    PRIVATE = "private"
    CLASS = "class"
    PUBLIC = "public"
    RESTRICTED = "restricted"

# ----------------------------------------------------------------------
# 2. MODEL: FileUpload (Bảng file_uploads)
# ----------------------------------------------------------------------

class FileUpload(Base):
    __tablename__ = "file_uploads"

    # 1. PRIMARY & IDENTIFICATION
    id = Column(UUID(as_uuid=True), primary_key=True, default=func.gen_random_uuid())
    filename = Column(String(255), nullable=False) # ID duy nhất (ví dụ: public_id của Cloudinary)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False) # URL hoặc Path lưu trữ (secure_url)
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    
    # 2. SECURITY & STATUS
    file_hash = Column(String(64), nullable=True) # SHA-256 for deduplication
    
    # 🌟 MAPPING ENUM: Sử dụng PgEnum để ánh xạ chính xác kiểu PostgreSQL
    upload_type = Column(Enum(UploadType, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='user_status'), nullable=False)
    is_processed = Column(Boolean, default=False)
    processing_status = Column(Enum(ProcessingStatus, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='user_status'), default=ProcessingStatus.PENDING, nullable=False)
    virus_scan_status = Column(Enum(ScanStatus, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='user_status'), default=ScanStatus.PENDING, nullable=False)
    virus_scan_result = Column(Text, nullable=True)
    access_level = Column(Enum(AccessLevel, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False, name='user_status'), default=AccessLevel.PUBLIC, nullable=False)
    
    # 3. RELATIONSHIPS & METADATA
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    associated_id = Column(UUID(as_uuid=True), nullable=True) 
    download_count = Column(Integer, default=0)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True) # TIMESTAMPTZ trong DB
    
    # 4. AUDIT COLUMNS (Nếu không được kế thừa từ Base)
    created_at = Column(TIMESTAMP(timezone=True), default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), default=func.now(), onupdate=func.now())
    
    # Relationships
    uploader = relationship("User", backref="uploaded_files")

    # 5. CHECK CONSTRAINTS
    __table_args__ = (
        # Đảm bảo kích thước file dương
        CheckConstraint(file_size > 0, name='check_file_size_positive'),
    )