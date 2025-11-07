from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.database import get_db
from app.dependencies import get_current_admin_user
from app.models.academic import Class
from app.routers.generator import create_crud_router
from app.schemas.classes import ClassResponse
from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from typing import List, Optional



# Generate base CRUD
base_router = create_crud_router(
    model=Class,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user,
    exclude_routes="list, get"
)

# Main router
router = APIRouter(tags=["Classes"])
router.include_router(base_router, prefix="")

@router.get("/classes", response_model=List[ClassResponse])
def list_classes(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    sort_by: Optional[str] = Query("created_at"),
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    search: Optional[str] = Query(None),
    include_deleted: bool = Query(False)
):
    """Danh sách lớp học có phân trang, sort, search và join các bảng liên quan"""

    # --- Base Query ---
    query = (
        db.query(Class)
        .options(
            joinedload(Class.course),
            joinedload(Class.teacher),
            joinedload(Class.substitute_teacher),
            joinedload(Class.room),
        )
    )

    # --- Filter ---
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

    # --- Pagination ---
    items = query.offset(skip).limit(limit).all()

    # --- Map ORM → ResponseSchema ---
    db_classes = db.query(Class).all()
    return [
        {
            **class_.__dict__,
            "course_name": class_.course.name if class_.course else None,
            "teacher_name": f"{class_.teacher.first_name} {class_.teacher.last_name}" if class_.teacher else None,
            "substitute_teacher_name": f"{class_.substitute_teacher.first_name} {class_.substitute_teacher.last_name}" if class_.substitute_teacher else None,
            "room_name": class_.room.name if class_.room else None,
        }
        for class_ in items
    ]

@router.get("/{class_id}", response_model=ClassResponse)
def get_class(class_id: UUID, db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=404, detail="Class not found")

    return ClassResponse.model_validate(c).model_copy(
        update={
            "course_name": c.course.name if c.course else None,
            "teacher_name": c.teacher.full_name if c.teacher else None,
            "substitute_teacher_name": c.substitute_teacher.full_name if c.substitute_teacher else None,
            "room_name": c.room.name if c.room else None,
        }
    )