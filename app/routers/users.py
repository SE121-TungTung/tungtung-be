from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies import get_current_active_user, get_current_admin_user, CommonQueryParams
from app.schemas.user import UserResponse, UserCreate, UserUpdate, UserPasswordUpdate, UserListResponse
from app.services.user import user_service
from app.models.user import User, UserRole, UserStatus
import uuid

router = APIRouter()

@router.get("/me", response_model=UserResponse)
async def read_user_me(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user profile"""
    return current_user

@router.put("/me", response_model=UserResponse)
async def update_user_me(
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update current user profile"""
    return await user_service.update_user(db, current_user.id, user_update)

@router.post("/me/change-password")
async def change_password(
    password_update: UserPasswordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Change current user password"""
    await user_service.change_password(db, current_user, password_update)
    return {"message": "Password changed successfully"}

@router.post("/", response_model=UserResponse)
async def create_user(
    user_create: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Create new user (admin only)"""
    return await user_service.create_user(db, user_create, current_user.id)

@router.get("/", response_model=UserListResponse)
async def list_users(
    commons: CommonQueryParams = Depends(),
    role: Optional[UserRole] = Query(None, description="Filter by user role"),
    search: Optional[str] = Query(None, description="Search in name and email"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """List users with filters (admin only)"""
    if search:
        users = await user_service.search_users(db, search, commons.skip, commons.limit)
    elif role:
        users = await user_service.get_users_by_role(db, role, commons.skip, commons.limit)
    else:
        users = await user_service.get_all(db, commons.skip, commons.limit)
    
    # Count total for pagination
    total = db.query(User).count()
    pages = (total + commons.limit - 1) // commons.limit

    users_schema = [UserResponse.model_validate(u) for u in users]

    return UserListResponse(
        users=[u.model_dump(mode="json") for u in users_schema],
        total=total,
        page=(commons.skip // commons.limit) + 1,
        size=commons.limit,
        pages=pages
    )

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Get user by ID (admin only)"""
    user = await user_service.get(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update user (admin only)"""
    return await user_service.update_user(db, user_id, user_update, id_updated_by=current_user.id)

@router.delete("/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Soft delete user (admin only)"""
    user = await user_service.get(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Soft delete by setting status to inactive
    await user_service.update_user(db, user_id, UserUpdate(status=UserStatus.INACTIVE))
    return {"message": "User deleted successfully"}
