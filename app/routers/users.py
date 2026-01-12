from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import get_db
from app.dependencies import get_current_active_user, get_current_admin_user, get_current_user, CommonQueryParams
from app.schemas.user import UserResponse, UserCreate, UserUpdate, UserPasswordUpdate, UserListResponse, BulkImportRequest, UserUpdateForm, ClassWithMembersResponse
from app.services.user import user_service
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
    if search:
        users = await user_service.search_users(db, search, commons.skip, commons.limit)
        search_filter = or_(
            User.first_name.ilike(f"%{search}%"),
            User.last_name.ilike(f"%{search}%"),
            User.email.ilike(f"%{search}%")
        )
        total = db.query(User).filter(search_filter, User.deleted_at.is_(None)).count()
    elif role:
        users = await user_service.get_users_by_role(db, role, commons.skip, commons.limit)
        total = db.query(User).filter(User.role == role, User.deleted_at.is_(None)).count()
    else:
        users = await user_service.get_all(db, commons.skip, commons.limit)
        total = db.query(User).filter(User.deleted_at.is_(None)).count()

    pages = (total + commons.limit - 1) // commons.limit

    users_schema = [UserResponse.model_validate(u) for u in users]

    return UserListResponse(
        users=[u.model_dump(mode="json") for u in users_schema],
        total=total,
        page=(commons.skip // commons.limit) + 1,
        size=commons.limit,
        pages=pages
    )

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

    class_ids: set = set()

    # Student
    enrollments = (
        db.query(ClassEnrollment)
        .filter(
            ClassEnrollment.student_id == current_user.id,
            ClassEnrollment.deleted_at.is_(None)
        )
        .all()
    )

    for enrollment in enrollments:
        class_ids.add(enrollment.class_id)

    # Teacher
    teaching_classes = (
        db.query(Class)
        .filter(
            Class.teacher_id == current_user.id,
            Class.deleted_at.is_(None)
        )
        .all()
    )

    for class_ in teaching_classes:
        class_ids.add(class_.id)

    if not class_ids:
        return []
    
    classes = (
        db.query(Class)
        .filter(
            Class.id.in_(list(class_ids)),
            Class.deleted_at.is_(None)
        )
        .all()
    )

    result = []

    for class_ in classes:
        classmates = (
            db.query(User)
            .join(ClassEnrollment, ClassEnrollment.student_id == User.id)
            .filter(
                ClassEnrollment.class_id == class_.id,
                User.deleted_at.is_(None),
                ClassEnrollment.deleted_at.is_(None)
            )
            .all()
        )

        sessions = (
            db.query(ClassSession)
            .filter(ClassSession.class_id == class_.id)
            .order_by(ClassSession.session_date, ClassSession.start_time)
            .all()
        )

        result.append({
            "id": class_.id,
            "name": class_.name,
            "teacher": {
                "id": class_.teacher.id if class_.teacher else None,
                "full_name": (
                    f"{class_.teacher.first_name} {class_.teacher.last_name}"
                    if class_.teacher else None
                ),
                "email": class_.teacher.email if class_.teacher else None,
                "avatar_url": class_.teacher.avatar_url if class_.teacher and class_.teacher.avatar_url else None
            },
            "students": [
                {
                    "id": student.id,
                    "full_name": f"{student.first_name} {student.last_name}",
                    "email": student.email,
                    "avatar_url": student.avatar_url if student.avatar_url else None
                }
                for student in classmates if student.id != current_user.id
            ],
            "sessions": sessions
        })

    return result

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
