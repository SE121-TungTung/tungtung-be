from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from typing import List, Optional

from app.core.database import get_db
from app.dependencies import get_current_admin_user, get_current_active_user, get_current_user, CommonQueryParams
from app.models.academic import Class
from app.routers.generator import create_crud_router
from app.schemas.classes import ClassResponse
from app.models.user import UserRole, User
from app.repositories.class_session import class_repository

# Step 1: Import core components
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException

# Generate base CRUD
base_router = create_crud_router(
    model=Class,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user,
    exclude_routes="list, get"
)

# Step 1: Khai báo Router với ResponseWrapperRoute
router = APIRouter(tags=["Classes"], route_class=ResponseWrapperRoute)
router.include_router(base_router, prefix="")

# ============================================================
# LIST CLASSES
# ============================================================
@router.get("/classes", response_model=PaginationResponse[ClassResponse])
def list_classes(
    params: CommonQueryParams = Depends(),
    sort_by: Optional[str] = Query("created_at"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    search: Optional[str] = Query(None),
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Danh sách lớp học có phân trang, sort, search và join các bảng liên quan"""

    query = (
        db.query(Class)
        .options(
            joinedload(Class.course),
            joinedload(Class.teacher),
            joinedload(Class.substitute_teacher),
            joinedload(Class.room),
        )
    )

    if not include_deleted:
        query = query.filter(Class.deleted_at.is_(None))

    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(Class.name.ilike(search_term))

    # --- Sort ---
    sort_column = getattr(Class, sort_by, None)
    if sort_column is not None:
        if sort_order.lower() == "desc":
            sort_column = sort_column.desc()
        query = query.order_by(sort_column)

    # Step 3: Xử lý Pagination
    total = query.count()
    items = query.offset(params.skip).limit(params.limit).all()

    result_data = [
        {
            **class_.__dict__,
            "course_name": class_.course.name if class_.course else None,
            "teacher_name": f"{class_.teacher.first_name} {class_.teacher.last_name}" if class_.teacher else None,
            "substitute_teacher_name": f"{class_.substitute_teacher.first_name} {class_.substitute_teacher.last_name}" if class_.substitute_teacher else None,
            "room_name": class_.room.name if class_.room else None,
        }
        for class_ in items
    ]

    return PaginationResponse(
        data=result_data,
        total=total,
        page=params.page,
        limit=params.limit
    )

# ============================================================
# GET CLASS DETAIL
# ============================================================
@router.get("/classes/{class_id}", response_model=ApiResponse[ClassResponse])
def get_class(class_id: UUID, db: Session = Depends(get_db), current_user = Depends(get_current_active_user)):
    c = (
        db.query(Class)
        .options(
            joinedload(Class.course),
            joinedload(Class.teacher),
            joinedload(Class.substitute_teacher),
            joinedload(Class.room),
        )
        .filter(Class.id == class_id)
        .first()
    )

    if not c:
        raise APIException(status_code=404, code="NOT_FOUND", message="Class not found")

    data = ClassResponse.model_validate(c).model_copy(
        update={
            "course_name": c.course.name if c.course else None,
            "teacher_name": c.teacher.full_name if c.teacher else None,
            "substitute_teacher_name": c.substitute_teacher.full_name if c.substitute_teacher else None,
            "room_name": c.room.name if c.room else None,
        }
    )
    return ApiResponse(data=data)

# ============================================================
# TEACHER CLASSES
# ============================================================
@router.get("/teacher/classes", response_model=PaginationResponse[ClassResponse])
def get_classes_by_teacher(
    params: CommonQueryParams = Depends(),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != UserRole.TEACHER:
        raise APIException(
            status_code=403, 
            code="FORBIDDEN", 
            message="Access forbidden: Only teachers can access their classes."
        )

    return class_repository.get_classes_by_teacher(
        db, 
        teacher_id=current_user.id,
        page=params.page,
        limit=params.limit
    )