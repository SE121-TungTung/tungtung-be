from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
import secrets
import random
from app.models.user import PasswordResetOTP

db = get_db()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def create_refresh_token(subject: Union[str, Any]) -> str:
    """Create refresh token (long-lived for remember me)"""
    expire = datetime.now() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode = {
        "exp": expire, 
        "sub": str(subject), 
        "type": "refresh",
        "jti": secrets.token_urlsafe(32)  # Unique token ID
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_password_reset_token(email: str, db: Session) -> str:
    # """Create password reset token"""
    # expire = datetime.now() + timedelta(minutes=settings.RESET_TOKEN_EXPIRE_MINUTES)
    
    # to_encode = {
    #     "exp": expire,
    #     "sub": email,
    #     "type": "reset"
    # }
    # return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    otp_code = ''.join(random.choices('0123456789', k=6))
    
    # Lưu vào DB thay vì encode JWT
    expires_at = datetime.utcnow() + timedelta(minutes=30)
    otp = PasswordResetOTP(
        email=email,
        otp_code=otp_code,
        expires_at=expires_at
    )
    db.add(otp)
    db.commit()
    
    return otp_code

def verify_password_reset_token(token: str, db: Session) -> Optional[str]:
    # """Verify and decode password reset token"""
    # try:
    #     payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    #     if payload.get("type") != "reset":
    #         return None
    #     email: str = payload.get("sub")
    #     return email
    # except JWTError:
    #     return None
    otp = db.query(PasswordResetOTP).filter_by(otp_code=token).first()
    
    if not otp or datetime.now(timezone.utc) > otp.expires_at:
        return None
    
    return otp.email

def create_access_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.email == username).first()
    if user is None:
        raise credentials_exception
    return user