from typing import Optional
from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token, 
    create_refresh_token, 
    verify_password_reset_token,
    is_refresh_token_revoked
)
# Step 1: Import core components
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse
from app.core.exceptions import APIException

from app.schemas.token import (
    Token, LoginRequest, LoginResponse, 
    PasswordResetRequest, PasswordResetConfirm, 
    PasswordResetResponse, RefreshTokenRequest
)
from app.services.user_service import user_service
from app.models.user import UserStatus
from app.repositories.user import user_repository

# Step 1: Khai báo Router với ResponseWrapperRoute
router = APIRouter(tags=["Auth"], prefix="/auth", route_class=ResponseWrapperRoute)

@router.post("/login", response_model=ApiResponse[LoginResponse])
async def login(
    db: Session = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """Form-based login (OAuth2 password form)"""
    user = await user_service.authenticate_user(db, form_data.username, form_data.password)
    
    if not user:
        raise APIException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_FAILED",
            message="Incorrect email or password"
        )
    
    if user.status != UserStatus.ACTIVE:
        raise APIException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="ACCOUNT_INACTIVE",
            message="Account is not active"
        )
    
    access_token = create_access_token(
        subject=user.email, 
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(subject=user.email)

    return ApiResponse(data={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "is_first_login": user.is_first_login
    })

@router.post("/login-json", response_model=ApiResponse[LoginResponse])
async def login_json(
    login_data: LoginRequest,
    db: Session = Depends(get_db)
):
    """Alternative login endpoint that accepts JSON"""
    user = await user_service.authenticate_user(db, login_data.email, login_data.password)
    
    if not user:
        raise APIException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_FAILED",
            message="Incorrect email or password"
        )
    
    access_token = create_access_token(
        subject=user.email, 
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh_token = create_refresh_token(subject=user.email)
    
    # Update last login
    user.last_login = datetime.utcnow()
    user.failed_login_attempts = 0
    db.commit()

    return ApiResponse(data={
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "is_first_login": user.is_first_login
    })

@router.post("/refresh", response_model=ApiResponse[Token])
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """Refresh access token using refresh token"""
    try:
        payload = jwt.decode(
            refresh_data.refresh_token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        
        if payload.get("type") != "refresh":
            raise APIException(status_code=401, code="INVALID_TOKEN_TYPE", message="Invalid token type")
        
        jti = payload.get("jti")
        if jti and is_refresh_token_revoked(jti):
            raise APIException(status_code=401, code="TOKEN_REVOKED", message="Token has been revoked")
        
        email: str = payload.get("sub")
        if email is None:
            raise APIException(status_code=401, code="INVALID_TOKEN", message="Invalid token")
        
        user = user_repository.get_by_email(db, email)
        if not user or user.status != "active":
            raise APIException(status_code=401, code="USER_INACTIVE", message="User not found or inactive")
        
        access_token = create_access_token(
            subject=email, 
            expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return ApiResponse(data={
            "access_token": access_token,
            "token_type": "bearer"
        })
        
    except JWTError:
        raise APIException(status_code=401, code="VALIDATION_FAILED", message="Could not validate credentials")

@router.post("/password-reset/request", response_model=ApiResponse[PasswordResetResponse])
async def request_password_reset(
    request: PasswordResetRequest,
    db: Session = Depends(get_db)
):
    """Request password reset - sends email with reset link"""
    user_email = await user_service.request_password_reset(db, request.email)

    if not user_email:
        return ApiResponse(data=PasswordResetResponse(
            message="Your email is not registered",
            detail="Please check and try again"
        ))
    
    return ApiResponse(data=PasswordResetResponse(
        message="If your email is registered, you will receive a password reset link",
        detail="Check your email inbox and spam folder"
    ))

@router.post("/password-reset/confirm", response_model=ApiResponse[PasswordResetResponse])
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
    
    return ApiResponse(data=PasswordResetResponse(
        message="Password has been reset successfully",
        detail="You can now login with your new password"
    ))

@router.post("/password-reset/validate-token", response_model=ApiResponse[dict])
async def validate_reset_token(token: str, db: Session = Depends(get_db)):
    """Validate if reset token is still valid"""
    email = verify_password_reset_token(token, db)
    
    if not email:
        raise APIException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="INVALID_TOKEN",
            message="Invalid or expired reset token"
        )
    
    return ApiResponse(data={"valid": True, "email": email})

@router.post("/logout", response_model=ApiResponse[dict])
async def logout(refresh_data: Optional[RefreshTokenRequest] = None):
    """Logout endpoint - revokes refresh token if provided"""
    await user_service.logout(refresh_token=refresh_data.refresh_token if refresh_data else None)
    return ApiResponse(data={"message": "Logout successful"})