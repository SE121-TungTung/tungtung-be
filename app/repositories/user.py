from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.repositories.base import BaseRepository
from app.models.user import User, UserRole, UserStatus
from app.core.security import get_password_hash, verify_password

from app.services.enrollment import class_enrollment_service

from fastapi import HTTPException, status

class UserRepository(BaseRepository[User]):
    def __init__(self):
        super().__init__(User)
    
    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        return db.query(User).filter(
            User.email == email,
            User.deleted_at.is_(None)).first()
    
    def create_user(self, db: Session, user_data: dict, default_class_id) -> User:
        try:
            # Hash password before creating
            if "password" in user_data:
                user_data["password_hash"] = get_password_hash(user_data.pop("password"))
            
            db_user = User(**user_data)
            
            db.add(db_user)
            db.flush()
            db.refresh(db_user)
            if user_data.get("role") == UserRole.STUDENT:
                if default_class_id is not None:
                    class_enrollment_service.create_auto_for_new_student(
                        db=db,
                        student_id=db_user.id,
                        default_class_id=default_class_id)
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Student class must be provided for student role"
                    )
            return db_user
        except Exception as e:
            db.rollback()
            raise e
    
    def authenticate(self, db: Session, email: str, password: str) -> Optional[User]:
        user = self.get_by_email(db, email)
        if not user or not verify_password(password, user.password_hash):
            return None
        return user
    
    def update_password(self, db: Session, user: User, new_password: str) -> User:
        user.password_hash = get_password_hash(new_password)
        user.must_change_password = False
        user.is_first_login = False
        db.commit()
        db.refresh(user)
        return user
    
    def get_users_by_role(self, db: Session, role: UserRole, skip: int = 0, limit: int = 100) -> List[User]:
        return (
            db.query(User)
            .filter(User.role == role, User.deleted_at.is_(None))
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def search_users(self, db: Session, query: str, skip: int = 0, limit: int = 100) -> List[User]:
        search_filter = or_(
            User.first_name.ilike(f"%{query}%"),
            User.last_name.ilike(f"%{query}%"),
            User.email.ilike(f"%{query}%")
        )
        return (
            db.query(User)
            .filter(search_filter, User.deleted_at.is_(None))
            .offset(skip)
            .limit(limit)
            .all()
        )

# Initialize repository instance
user_repository = UserRepository()
