from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status, BackgroundTasks
from app.services.base import BaseService
from app.repositories.user import user_repository
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate, UserPasswordUpdate, BulkImportRequest
from app.core.security import verify_password, get_password_hash, create_password_reset_token, verify_password_reset_token
from app.services.email import email_service
from app.dependencies import generate_strong_password
from app.services.email import email_service
import uuid
import logging

from app.services.notification import notification_service
from app.models.notification import NotificationPriority, NotificationType
from app.schemas.notification import NotificationCreate

from uuid import UUID

from datetime import date
from sqlalchemy import func

from app.models.academic import Class, Course, ClassEnrollment, EnrollmentStatus, ClassStatus
from app.models.test import TestAttempt, Test, AttemptStatus
from app.models.session_attendance import ClassSession
from app.models.session_attendance import SessionStatus
from app.models.user import UserStatus

logger = logging.getLogger(__name__)
from datetime import datetime
from fastapi import UploadFile
from app.services import cloudinary

from app.services.audit_log import audit_service
from app.models.audit_log import AuditAction


class UserService(BaseService):
    def __init__(self):
        super().__init__(user_repository)
        self.repository = user_repository
    
    async def create_user(self, db: Session, user_create: UserCreate, created_by: Optional[uuid.UUID] = None, default_class_id: Optional[uuid.UUID] = None, background_tasks: BackgroundTasks = None) -> User:
        try:
            # Check if a non-deleted user already exists
            existing_user = self.repository.get_by_email(db, user_create.email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )

            # If there's a soft-deleted user with the same email, proceed to
            # create a new user with a new identity and leave the old row alone.
            deleted_conflict = db.query(User).filter(User.email == user_create.email, User.deleted_at.isnot(None)).first()
            if deleted_conflict:
                logger.info(
                    "Creating new user with email %s while a soft-deleted user exists (id=%s). Keeping old record.",
                    user_create.email,
                    deleted_conflict.id
                )
            
            password = generate_strong_password()
            print(f"Generated password for {user_create.email}: {password}")

            user_data = user_create.model_dump()
            user_data["password_hash"] = get_password_hash(password)
            user_data["created_by"] = created_by
            user_data["updated_by"] = created_by
            
            new_user = self.repository.create_user(db, user_data, default_class_id=default_class_id)
            
            full_name = f"{new_user.first_name} {new_user.last_name}"

            if background_tasks:
                background_tasks.add_task(
                    email_service.send_account_creation_email,
                    "khoiluub143@gmail.com",
                    full_name,
                    password,
                    new_user.role.value
                )
            
            audit_service.log(
                db=db,
                user_id=created_by,
                action=AuditAction.CREATE,
                table_name="users",
                record_id=new_user.id,
                old_values=None,
                new_values={
                    "email": new_user.email,
                    "role": new_user.role.value,
                    "status": new_user.status,
                    "created_by": str(created_by) if created_by else None
                }
            )

            await notification_service.send_notification(
                db=db,
                noti_info=NotificationCreate(
                    user_id=new_user.id,
                    title="Tài khoản đã được tạo",
                    content="Tài khoản của bạn đã được tạo thành công. Vui lòng kiểm tra email để nhận thông tin đăng nhập.",
                    notification_type=NotificationType.SYSTEM_ALERT,
                    priority=NotificationPriority.NORMAL,
                    action_url="/login"
                )
            )
            db.commit()
            return new_user
        except Exception as e:
            raise e
        
    async def bulk_create_users(self, db: Session, request: BulkImportRequest, created_by: Optional[uuid.UUID] = None) -> List[User]:
        """Bulk create users, generate password and send email for each."""
        created_users = []
         
        # Lặp qua danh sách users từ request.users
        for user_data_in in request.users: # <-- Lặp trên request.users
            try:
                # 1. Check if user already exists
                existing_user = self.repository.get_by_email(db, user_data_in.email)
                if existing_user:
                    print(f"User {user_data_in.email} skipped: Already registered.")
                    continue

                # 2. TẠO VÀ KIỂM TRA MẬT KHẨU
                raw_password = generate_strong_password()
                hashed_password = get_password_hash(raw_password)
                print(f"Generated password for {user_data_in.email}: {raw_password}")

                # Dùng jsonable_encoder để chuyển đổi Pydantic sang Dict
                user_data = user_data_in.model_dump(
                    exclude_unset=True, 
                    exclude={'class_id'}
                )
                user_data.update({
                    "password_hash": hashed_password,
                    "must_change_password": True, 
                    "created_by": created_by,
                    "updated_by": created_by
                })
                
                # 3. TẠO USER
                new_user = self.repository.create_user(db, user_data, default_class_id=user_data_in.class_id)
                created_users.append(new_user)
                
                # 4. GỬI EMAIL
                full_name = f"{new_user.first_name} {new_user.last_name}"
                await email_service.send_account_creation_email("khoiluub143@gmail.com", full_name, raw_password, new_user.role)
                audit_service.log(
                    db=db,
                    user_id=created_by,
                    action=AuditAction.CREATE,
                    table_name="users",
                    record_id=new_user.id,
                    old_values=None,
                    new_values={
                        "email": new_user.email,
                        "role": new_user.role.value,
                        "status": new_user.status,
                        "created_by": str(created_by) if created_by else None
                    }
                )
                await notification_service.send_notification(
                    db=db,
                    noti_info=NotificationCreate(
                        user_id=new_user.id,
                        title="Tài khoản đã được tạo",
                        content="Tài khoản của bạn đã được tạo. Vui lòng kiểm tra email để nhận mật khẩu đăng nhập.",
                        notification_type=NotificationType.SYSTEM_ALERT,
                        priority=NotificationPriority.NORMAL,
                        action_url="/login"
                    )
                )
            except Exception as e:
                print(f"Error creating user {user_data_in.email}: {e}")
                # Tiếp tục vòng lặp

        db.commit()
        return created_users
    
    async def authenticate_user(self, db: Session, email: str, password: str) -> Optional[User]:
        user = self.repository.authenticate(db, email, password)
        if not user:
            return None
        
        # Update last login
        user.last_login = datetime.now()
        user.failed_login_attempts = 0

        audit_service.log(
            db=db,
            user_id=user.id,
            action=AuditAction.LOGIN,
            table_name="users",
            record_id=user.id,
            old_values=None,
            new_values={
                "last_login": user.last_login.isoformat()
            }
        )
        db.commit()
        return user
    
    async def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        return self.repository.get_by_email(db, email)
    
    async def update_user(self, db: Session, user_id: uuid.UUID, user_update: UserUpdate, avatar_file: Optional[UploadFile], id_updated_by) -> User:
        user = await self.get(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        if avatar_file:
            try:
                # Gọi File Service để upload lên Cloudinary
                upload_result = await cloudinary.upload_and_save_metadata(
                    db=db, 
                    uploaded_file=avatar_file, 
                    user_id=user_id,
                    folder="user_avatars"
                )
                
                avatar_url = upload_result.file_path 

                # Tùy chọn: Xóa avatar cũ khỏi Cloudinary nếu cần
                # if user.avatar_url:
                #     file_service.delete_file_by_url(user.avatar_url) 
                
                update_data = user_update.model_dump(exclude_unset=True)
                update_data['avatar_url'] = avatar_url
                
            except HTTPException as e:
                raise HTTPException(status_code=400, detail=f"Failed to upload avatar: {e.detail}")
        
        else:
            update_data = user_update.model_dump(exclude_unset=True)
        update_data["updated_by"] = id_updated_by
        
        old_values = {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "avatar_url": user.avatar_url,
            "status": user.status
        }
        audit_service.log(
            db=db,
            user_id=id_updated_by,
            action=AuditAction.UPDATE,
            table_name="users",
            record_id=user.id,
            old_values=old_values,
            new_values=update_data
        )

        if "status" in update_data or "role" in update_data:
            await notification_service.send_notification(
                db=db,
                noti_info=NotificationCreate(
                    user_id=user.id,
                    title="Thông tin tài khoản đã được cập nhật",
                    content="Quản trị viên đã cập nhật trạng thái hoặc quyền của tài khoản bạn.",
                    notification_type=NotificationType.SYSTEM_ALERT,
                    priority=NotificationPriority.NORMAL,
                    action_url="/profile"
                )
            )


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
            email="khoiluub143@gmail.com",
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

        await notification_service.send_notification(
            db=db,
            noti_info=NotificationCreate(
                user_id=user.id,
                title="Mật khẩu đã được thay đổi",
                content="Mật khẩu tài khoản của bạn vừa được thay đổi thành công. Nếu không phải bạn thực hiện, hãy liên hệ hỗ trợ ngay.",
                notification_type=NotificationType.SYSTEM_ALERT,
                priority=NotificationPriority.HIGH,
                action_url="/change-password"
            )
        )

        db.commit()
        db.refresh(user)
        
        return user
    
    async def logout(self, refresh_token: Optional[str] = None) -> bool:
        """Logout the current user. If a refresh token is provided, revoke it so it cannot be used to obtain new access tokens.
        Note: This uses an in-memory revocation list; in production consider persisting revocations (Redis/DB)."""
        from app.core.security import revoke_refresh_token

        if refresh_token:
            revoked = revoke_refresh_token(refresh_token)
            if not revoked:
                # Invalid refresh token provided
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid refresh token")
            return True

        # If no refresh token provided, there's nothing to revoke on server side.
        # Clients should delete tokens locally (e.g., from cookies/localStorage).
        return True
    
    async def get_users_by_role(self, db: Session, role: UserRole, skip: int = 0, limit: int = 100) -> List[User]:
        return self.repository.get_users_by_role(db, role, skip, limit)
    
    async def search_users(self, db: Session, query: str, skip: int = 0, limit: int = 100) -> List[User]:
        return self.repository.search_users(db, query, skip, limit)
    
    async def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        return self.repository.get_all(db, skip, limit)
    
    def get_user_overview(self, db: Session, current_user: User) -> dict:
        role = current_user.role
        today = date.today()

        if role == UserRole.STUDENT:
            return self._get_student_stats(db, current_user.id, today)
        elif role == UserRole.TEACHER:
            return self._get_teacher_stats(db, current_user.id, today)
        elif role in [UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN]:
            return self._get_center_admin_stats(db, today)
        elif role == UserRole.SYSTEM_ADMIN:
            return self._get_system_admin_stats(db)
        
        return {}

    def _get_student_stats(self, db: Session, student_id: UUID, today: date) -> dict:
        active_courses_count = (
            db.query(ClassEnrollment)
            .filter(ClassEnrollment.student_id == student_id, ClassEnrollment.status == EnrollmentStatus.ACTIVE)
            .count()
        )

        upcoming_sessions_count = (
            db.query(ClassSession)
            .join(Class, ClassSession.class_id == Class.id)
            .join(ClassEnrollment, ClassEnrollment.class_id == Class.id)
            .filter(
                ClassEnrollment.student_id == student_id,
                ClassEnrollment.status == EnrollmentStatus.ACTIVE,
                ClassSession.session_date >= today,
                ClassSession.status == SessionStatus.SCHEDULED
            )
            .count()
        )

        attempts_query = db.query(TestAttempt.total_score).filter(
            TestAttempt.student_id == student_id,
            TestAttempt.status == AttemptStatus.GRADED
        )
        tests_taken = attempts_query.count()
        
        total_score = sum(a[0] for a in attempts_query.all() if a[0] is not None)
        avg_score = round(total_score / tests_taken, 2) if tests_taken > 0 else 0.0

        return {
            "role": "student",
            "active_courses": active_courses_count,
            "upcoming_sessions_count": upcoming_sessions_count,
            "tests_taken": tests_taken,
            "average_test_score": avg_score
        }

    def _get_teacher_stats(self, db: Session, teacher_id: UUID, today: date) -> dict:
        active_classes_count = db.query(Class).filter(
            Class.teacher_id == teacher_id, 
            Class.status == ClassStatus.ACTIVE
        ).count()

        total_students = (
            db.query(ClassEnrollment.student_id)
            .join(Class, ClassEnrollment.class_id == Class.id)
            .filter(Class.teacher_id == teacher_id, ClassEnrollment.status == EnrollmentStatus.ACTIVE)
            .distinct()
            .count()
        )

        sessions_today = (
            db.query(ClassSession)
            .filter(
                ClassSession.teacher_id == teacher_id,
                ClassSession.session_date == today,
                ClassSession.status == SessionStatus.SCHEDULED
            )
            .count()
        )
        
        pending_grading = (
            db.query(TestAttempt)
            .join(Test, TestAttempt.test_id == Test.id)
            .filter(Test.created_by == teacher_id, TestAttempt.status == AttemptStatus.SUBMITTED)
            .count()
        )

        return {
            "role": "teacher",
            "active_classes": active_classes_count,
            "total_students": total_students,
            "sessions_today": sessions_today,
            "pending_grading_count": pending_grading
        }

    def _get_center_admin_stats(self, db: Session, today: date) -> dict:

        total_students = db.query(User).filter(
            User.role == UserRole.STUDENT,
            User.status == UserStatus.ACTIVE
        ).count()

        total_teachers = db.query(User).filter(
            User.role == UserRole.TEACHER,
            User.status == UserStatus.ACTIVE
        ).count()

        active_classes = db.query(Class).filter(
            Class.status == ClassStatus.ACTIVE
        ).count()

        sessions_today = db.query(ClassSession).join(Class).filter(
            ClassSession.session_date == today
        ).count()

        return {
            "role": "center_admin",
            "total_students": total_students,
            "total_teachers": total_teachers,
            "active_classes": active_classes,
            "sessions_today_count": sessions_today
        }

    def _get_system_admin_stats(self, db: Session) -> dict:
        total_users = db.query(User).count()
        total_courses = db.query(Course).count()
        active_classes = db.query(Class).filter(Class.status == ClassStatus.ACTIVE).count()
        
        users_by_role = (
            db.query(User.role, func.count(User.id))
            .group_by(User.role)
            .all()
        )
        user_distribution = {role.value: count for role, count in users_by_role}

        return {
            "role": "system_admin",
            "total_users": total_users,
            "total_courses": total_courses,
            "total_active_classes": active_classes,
            "user_distribution": user_distribution
        }
      

# Initialize service instance
user_service = UserService()
