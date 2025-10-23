from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.services.base import BaseService
from app.repositories.user import user_repository
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate, UserPasswordUpdate, UserResponse, UserListResponse
from app.core.security import verify_password, get_password_hash, create_password_reset_token, verify_password_reset_token
from app.services.email import email_service
import uuid
from datetime import datetime

class UserService(BaseService):
    def __init__(self):
        super().__init__(user_repository)
        self.repository = user_repository
    
    async def create_user(self, db: Session, user_create: UserCreate, created_by: Optional[uuid.UUID] = None) -> User:
        # Check if user already exists
        existing_user = self.repository.get_by_email(db, user_create.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        user_data = user_create.dict()
        user_data["created_by"] = created_by
        
        return self.repository.create_user(db, user_data)
    
    async def authenticate_user(self, db: Session, email: str, password: str) -> Optional[User]:
        user = self.repository.authenticate(db, email, password)
        if not user:
            return None
        
        # Update last login
        user.last_login = datetime.now()
        user.failed_login_attempts = 0
        db.commit()
        return user
    
    async def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        return self.repository.get_by_email(db, email)
    
    async def update_user(self, db: Session, user_id: uuid.UUID, user_update: UserUpdate, id_updated_by) -> User:
        user = await self.get(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        update_data = user_update.model_dump(exclude_unset=True)
        update_data["updated_by"] = id_updated_by
        return self.repository.update(db, db_obj=user, obj_in=update_data)
    
    async def change_password(self, db: Session, user: User, password_update: UserPasswordUpdate) -> User:
        # Verify current password
        if not verify_password(password_update.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect current password"
            )
        
        return self.repository.update_password(db, user, password_update.new_password)
    
    async def request_password_reset(self, db: Session, email: str) -> bool:
        """Request password reset - send email with token"""
        user = self.repository.get_by_email(db, email)
        
        # Don't reveal if user exists or not for security
        if not user:
            # Still return success to prevent email enumeration
            return False
        
        # Create reset token
        reset_token = create_password_reset_token(user.email, db)
        
        # Send email
        await email_service.send_password_reset_email(
            email=user.email,
            username=f"{user.first_name} {user.last_name}",
            reset_token=reset_token
        )
        
        return True
    
    async def reset_password(
        self, 
        db: Session, 
        token: str, 
        new_password: str
    ) -> User:
        """Reset password using token"""
        # Verify token
        email = verify_password_reset_token(token, db)
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        # Get user
        user = self.repository.get_by_email(db, email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update password
        user.password_hash = get_password_hash(new_password)
        user.must_change_password = False
        user.is_first_login = False
        user.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(user)
        
        return user
    
    async def get_users_by_role(self, db: Session, role: UserRole, skip: int = 0, limit: int = 100) -> List[User]:
        return self.repository.get_users_by_role(db, role, skip, limit)
    
    async def search_users(self, db: Session, query: str, skip: int = 0, limit: int = 100) -> List[User]:
        return self.repository.search_users(db, query, skip, limit)
    
    async def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        return self.repository.get_all(db, skip, limit)
      

# Initialize service instance
user_service = UserService()
