"""
ClassEnrollment Router

Sử dụng generic CRUD cho create/update/delete,
nhưng override GET endpoints để thêm student_name và class_name vào response.
"""
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
import math

from app.core.database import get_db
from app.dependencies import get_current_admin_user, require_any_role
from app.models.academic import ClassEnrollment, Class
from app.models.user import User, UserRole
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.schemas.enrollment import ClassEnrollmentResponse
from app.routers.generator import create_crud_router

# Shorthand role dependencies
AdminUp = Depends(require_any_role(
    UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN
))

# Generate base CRUD (create, update, delete only)
base_router = create_crud_router(
    model=ClassEnrollment,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user,
    tag_prefix="Class Enrollment",
    exclude_routes=["list", "get"],  # Override these below
)

# Main router
router = APIRouter()
router.include_router(base_router, prefix="")


def _enrich_enrollment(db: Session, enrollment: ClassEnrollment) -> ClassEnrollmentResponse:
    """Attach student_name and class_name to an enrollment record."""
    data = ClassEnrollmentResponse.model_validate(enrollment)

    # Get student name
    student = db.query(User.first_name, User.last_name).filter(
        User.id == enrollment.student_id
    ).first()
    if student:
        data.student_name = f"{student.last_name} {student.first_name}"

    # Get class name
    cls = db.query(Class.name).filter(Class.id == enrollment.class_id).first()
    if cls:
        data.class_name = cls.name

    return data


@router.get(
    "/classenrollments",
    response_model=PaginationResponse[ClassEnrollmentResponse],
    summary="List class enrollments",
    tags=["Class Enrollment"],
)
async def list_enrollments(
    class_id: Optional[UUID] = Query(None, description="Lọc theo lớp"),
    student_id: Optional[UUID] = Query(None, description="Lọc theo học sinh"),
    status: Optional[str] = Query(None, description="Lọc theo trạng thái (active, completed, dropped...)"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = AdminUp,
):
    query = db.query(ClassEnrollment).filter(ClassEnrollment.deleted_at.is_(None))

    if class_id:
        query = query.filter(ClassEnrollment.class_id == class_id)
    if student_id:
        query = query.filter(ClassEnrollment.student_id == student_id)
    if status:
        query = query.filter(ClassEnrollment.status == status)

    total = query.count()
    enrollments = (
        query
        .order_by(ClassEnrollment.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    items = [_enrich_enrollment(db, e) for e in enrollments]
    meta = PaginationMetadata(
        page=page, limit=limit, total=total,
        total_pages=math.ceil(total / limit) if limit else 0,
    )
    return PaginationResponse(success=True, data=items, meta=meta, message="Thành công")


@router.get(
    "/classenrollments/{enrollment_id}",
    response_model=ApiResponse[ClassEnrollmentResponse],
    summary="Get class enrollment detail",
    tags=["Class Enrollment"],
)
async def get_enrollment(
    enrollment_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = AdminUp,
):
    enrollment = db.query(ClassEnrollment).filter(
        ClassEnrollment.id == enrollment_id,
        ClassEnrollment.deleted_at.is_(None),
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký")

    item = _enrich_enrollment(db, enrollment)
    return ApiResponse(success=True, data=item, message="Thành công")