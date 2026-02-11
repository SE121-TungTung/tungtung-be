from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import get_db
from app.dependencies import get_current_active_user, get_current_admin_user, get_current_user, CommonQueryParams
from app.schemas.user import UserResponse, UserCreate, UserUpdate, UserPasswordUpdate, UserListResponse, BulkImportRequest, UserUpdateForm, ClassWithMembersResponse
from app.services.user_service import user_service
from app.models.user import User, UserRole, UserStatus
from app.models.academic import ClassEnrollment, Class
import json
from uuid import UUID
from app.routers.generator import create_crud_router
from app.models.session_attendance import ClassSession

delete_user_router = create_crud_router(
    model=User,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user,
    exclude_routes=["create", "update", "list", "get"],
    prefix=""
)

router = APIRouter()
router.include_router(delete_user_router, prefix="")

@router.get("/me", response_model=UserResponse)
async def read_user_me(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user profile"""
    return current_user

@router.put("/me")
async def update_me(
    first_name: str | None = Form(None),
    last_name: str | None = Form(None),
    phone: str | None = Form(None),
    address: str | None = Form(None),
    emergency_contact: str | None = Form(None),
    preferences: str | None = Form(None),
    avatar_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    user_update = UserUpdate(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        address=address,
        emergency_contact=json.loads(emergency_contact) if emergency_contact else None,
        preferences=json.loads(preferences) if preferences else None,
    )

    return await user_service.update_user(
        db=db,
        user_id=current_user.id,
        user_update=user_update,
        avatar_file=avatar_file,
        id_updated_by=current_user.id
    )

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
    background_tasks: BackgroundTasks,
    default_class_id: Optional[UUID] = Query(
        None, 
        description="ID của lớp học mà sinh viên sẽ được tự động gán vào (Enrollment ban đầu)"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
    
):
    """Create new user (admin only)"""
    return await user_service.create_user(db, user_create, current_user.id, default_class_id=default_class_id, background_tasks=background_tasks)

@router.post("/bulk", response_model=List[UserResponse], status_code=status.HTTP_201_CREATED)
async def bulk_create_users(
    request: BulkImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Bulk create users from a list with auto-generated passwords and email notifications (admin only)."""
    return await user_service.bulk_create_users(db, request, current_user.id)

@router.get("/", response_model=UserListResponse)
async def list_users(
    commons: CommonQueryParams = Depends(),
    role: Optional[UserRole] = Query(None, description="Filter by user role"),
    search: Optional[str] = Query(None, description="Search in name and email"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List users with filters (admin only)"""
    return user_service.get_list_user(commons=commons, role=role, search=search, db=db, current_user=current_user)

@router.get("/overview", response_model=dict)
async def get_user_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get user overview statistics"""
    return user_service.get_user_overview(db, current_user=current_user)

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
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

@router.get("/me/classes", response_model=list[ClassWithMembersResponse])
async def get_my_classes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Lấy danh sách lớp mà user hiện tại tham gia:
    - Student: lớp đã enroll
    - Teacher: lớp đang giảng dạy
    Trả về kèm giáo viên, danh sách học sinh và sessions
    """
    return user_service.get_my_classes(db=db, current_user=current_user)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    update_form: UserUpdateForm = Depends(),
    avatar_file: Optional[UploadFile] = File(None, description="Avatar image file"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Update user (admin only)"""
    user_update = update_form.to_update_schema(UserUpdate)
    return await user_service.update_user(db, user_id, user_update, avatar_file, id_updated_by=current_user.id)
