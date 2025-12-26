from typing import Optional
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.schemas.token import Token, LoginRequest, LoginResponse, PasswordResetRequest
from app.services.user import user_service
from app.models.user import UserStatus
from app.schemas.token import PasswordResetConfirm, PasswordResetResponse
from app.core.security import verify_password_reset_token, create_refresh_token
from app.schemas.token import RefreshTokenRequest
from app.repositories.user import user_repository
from datetime import datetime

router = APIRouter()

@router.post("/login", response_model=LoginResponse)
async def login(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
    remember_me: bool = False
):
    """Form-based login (OAuth2 password form)"""
    
    user = await user_service.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is not active",
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.email, expires_delta=access_token_expires
    )

    
    refresh_token = create_refresh_token(subject=user.email)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "is_first_login": user.is_first_login
    }

@router.post("/login-json", response_model=LoginResponse)
async def login_json(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """Alternative login endpoint that accepts JSON"""
    user = await user_service.authenticate_user(db, login_data.email, login_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.email, expires_delta=access_token_expires
    )

    refresh_token = create_refresh_token(subject=user.email)
    
    # Update last login
    user.last_login = datetime.utcnow()
    user.failed_login_attempts = 0
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "is_first_login": user.is_first_login
    }

@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """Refresh access token using refresh token"""
    from jose import jwt, JWTError
    from app.core.security import is_refresh_token_revoked
    
    try:
        payload = jwt.decode(
            refresh_data.refresh_token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        # Check revocation
        jti = payload.get("jti")
        if jti and is_refresh_token_revoked(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked"
            )
        
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        # Verify user still exists and is active
        user = user_repository.get_by_email(db, email)
        if not user or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Create new access token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            subject=email, expires_delta=access_token_expires
        )
        
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

@router.post("/password-reset/request", response_model=PasswordResetResponse)
async def request_password_reset(
    request: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """Request password reset - sends email with reset link"""
    
    user_email = await user_service.request_password_reset(db, request.email)

    if not user_email:
        return PasswordResetResponse(
            message="Your email is not registered",
            detail="Please check and try again"
        )
    
    return PasswordResetResponse(
        message="If your email is registered, you will receive a password reset link",
        detail="Check your email inbox and spam folder"
    )

@router.post("/password-reset/confirm", response_model=PasswordResetResponse)
async def confirm_password_reset(
    reset_data: PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    """Confirm password reset with (token) otp"""
    await user_service.reset_password(
        db, 
        reset_data.token, 
        reset_data.new_password
    )
    
    return PasswordResetResponse(
        message="Password has been reset successfully",
        detail="You can now login with your new password"
    )

@router.post("/password-reset/validate-token")
async def validate_reset_token(token: str, db: Session = Depends(get_db)):
    """Validate if reset token is still valid"""
    email = verify_password_reset_token(token, db)
    
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    return {"valid": True, "email": email}

@router.post("/logout")
async def logout(refresh_data: Optional[RefreshTokenRequest] = None):
    """Logout endpoint - revokes refresh token if provided"""
    await user_service.logout(refresh_token=refresh_data.refresh_token if refresh_data else None)
    return {"message": "Logout successful"}

