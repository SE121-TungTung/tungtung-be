from sqlalchemy import Column, String, Enum, Boolean, Date, JSON, Text, Integer, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import BaseModel
import enum

class UserRole(enum.Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    OFFICE_ADMIN = "office_admin"
    CENTER_ADMIN = "center_admin"
    SYSTEM_ADMIN = "system_admin"

class UserStatus(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_ACTIVATION = "pending_activation"

class User(BaseModel):
    __tablename__ = "users"
    
    # Basic info
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False), default=UserRole.STUDENT, nullable=False)
    status = Column(Enum(UserStatus, values_callable=lambda obj: [e.value for e in obj], 
        native_enum=False), default=UserStatus.ACTIVE, nullable=False)
    
    # Personal info
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20), index=True)
    avatar_url = Column(Text)
    date_of_birth = Column(Date)
    address = Column(Text)
    
    # Additional data
    emergency_contact = Column(JSON)  # {name, phone, relationship}
    preferences = Column(JSON, default={})
    
    # Security
    last_login = Column(TIMESTAMP(timezone=True))
    is_first_login = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(TIMESTAMP(timezone=True))
    
    # Audit
    created_by = Column(UUID, nullable=True)
    updated_by = Column(UUID, nullable=True)

# class PasswordResetToken(BaseModel):
#     __tablename__ = "password_reset_tokens"
    
#     user_id = Column(UUID, nullable=False, index=True)
#     token = Column(String(255), unique=True, nullable=False, index=True)
#     expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
#     used = Column(Boolean, default=False)

class PasswordResetOTP(BaseModel):
    __tablename__ = "password_reset_otps"
    
    email = Column(String(255), nullable=False, index=True)
    otp_code = Column(String(6), nullable=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)