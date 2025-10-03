from pydantic_settings import BaseSettings
from typing import Optional
import secrets


class Settings(BaseSettings):
    PROJECT_NAME: str
    VERSION: str
    API_V1_STR: str
    
    # Database
    DATABASE_URL: str
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int
    RESET_TOKEN_EXPIRE_MINUTES: int
    
    # Redis
    REDIS_URL: str
    
    # CORS
    BACKEND_CORS_ORIGINS: list[str]

    # Email Configuration
    MAIL_USERNAME: Optional[str]
    MAIL_PASSWORD: Optional[str]
    MAIL_FROM: Optional[str]
    MAIL_PORT: int = 587
    MAIL_SERVER: Optional[str]
    MAIL_FROM_NAME: str
    MAIL_STARTTLS: bool
    MAIL_SSL_TLS: bool
    USE_CREDENTIALS: bool
    VALIDATE_CERTS: bool
    
    # Frontend URL for reset links
    FRONTEND_URL: str
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()