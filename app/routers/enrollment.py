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
from app.models.academic import ClassEnrollment, Class, ClassStatus, PaymentStatus, EnrollmentStatus
from app.models.finance import Invoice, InvoiceStatus
from app.models.user import User, UserRole
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.schemas.enrollment import ClassEnrollmentResponse
from app.routers.generator import create_crud_router
from pydantic import BaseModel
from decimal import Decimal
from datetime import datetime, timezone, timedelta

# Shorthand role dependencies
AdminUp = Depends(require_any_role(
    UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN
))

# Generate base CRUD (update, delete only)
base_router = create_crud_router(
    model=ClassEnrollment,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user,
    tag_prefix="Class Enrollment",
    exclude_routes=["list", "get", "create"],  # Exclude create route
)

class ClassEnrollmentCreate(BaseModel):
    class_id: UUID
    student_id: UUID
    notes: Optional[str] = None


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


@router.post(
    "/classenrollments",
    response_model=ApiResponse[ClassEnrollmentResponse],
    status_code=201,
    summary="Create class enrollment with invoice",
    tags=["Class Enrollment"],
)
@router.post(
    "/classenrollments/",
    response_model=ApiResponse[ClassEnrollmentResponse],
    status_code=201,
    summary="Create class enrollment with invoice (trailing slash)",
    tags=["Class Enrollment"],
    include_in_schema=False,
)
async def create_enrollment(
    payload: ClassEnrollmentCreate,
    db: Session = Depends(get_db),
    current_user: User = AdminUp,
):
    # 1. Check if class exists
    class_obj = db.query(Class).filter(Class.id == payload.class_id, Class.deleted_at.is_(None)).first()
    if not class_obj:
        raise HTTPException(status_code=404, detail="Không tìm thấy lớp học")

    # 2. Check if class status is OPEN
    if class_obj.status != ClassStatus.OPEN:
        raise HTTPException(status_code=400, detail="Lớp học không ở trạng thái mở đăng ký (OPEN)")

    # 3. Check if current_students < max_students
    if class_obj.current_students >= class_obj.max_students:
        raise HTTPException(status_code=400, detail="Lớp học đã đạt sĩ số tối đa (đầy lớp)")

    # 4. Check if student exists
    student_obj = db.query(User).filter(User.id == payload.student_id, User.deleted_at.is_(None)).first()
    if not student_obj:
        raise HTTPException(status_code=404, detail="Không tìm thấy học sinh")

    # 5. Check if already enrolled
    existing = db.query(ClassEnrollment).filter(
        ClassEnrollment.class_id == payload.class_id,
        ClassEnrollment.student_id == payload.student_id,
        ClassEnrollment.deleted_at.is_(None)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Học viên đã đăng ký lớp học này trước đó")

    # 6. Create enrollment (pending payment, status active)
    enrollment = ClassEnrollment(
        class_id=payload.class_id,
        student_id=payload.student_id,
        payment_status=PaymentStatus.PENDING,
        status=EnrollmentStatus.ACTIVE,
        notes=payload.notes,
        created_by=current_user.id
    )
    db.add(enrollment)
    db.flush() # To get enrollment.id

    # 7. Create invoice
    # Set due date to 7 days from now or class start_date, whichever is sooner
    due_date = datetime.now(timezone.utc) + timedelta(days=7)
    if class_obj.start_date:
        class_start_datetime = datetime.combine(class_obj.start_date, datetime.min.time(), tzinfo=timezone.utc)
        if class_start_datetime < due_date:
            due_date = class_start_datetime

    invoice = Invoice(
        student_id=payload.student_id,
        enrollment_id=enrollment.id,
        original_amount=Decimal(str(class_obj.fee_amount)),
        discount_amount=Decimal("0.0"),
        final_amount=Decimal(str(class_obj.fee_amount)),
        status=InvoiceStatus.PENDING,
        due_date=due_date,
        notes=f"Hóa đơn đăng ký lớp {class_obj.name}",
        created_by=current_user.id
    )
    db.add(invoice)

    # 8. Increment class current students
    class_obj.current_students = class_obj.current_students + 1
    
    db.commit()
    db.refresh(enrollment)

    # Enrich response
    item = _enrich_enrollment(db, enrollment)
    return ApiResponse(success=True, data=item, message="Đăng ký lớp học thành công")