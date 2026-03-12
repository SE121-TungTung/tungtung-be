from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.dependencies import get_current_admin_user, CommonQueryParams
from app.models.academic import Course
from app.services.course_service import course_service
from app.routers.generator import create_crud_router

from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import PaginationResponse
from app.schemas.course import CourseResponse

# Generate base CRUD
base_router = create_crud_router(
    model=Course,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user
)

router = APIRouter(tags=["Courses"], route_class=ResponseWrapperRoute)
router.include_router(base_router, prefix="")

# ============================================================
# CUSTOM ENDPOINTS
# ============================================================

@router.get("/active", response_model=PaginationResponse[CourseResponse])
async def get_active_courses(
    params: CommonQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """Get all active courses with pagination"""
    return await course_service.get_active_courses(
        db=db, 
        page=params.page, 
        limit=params.limit
    )

@router.get("/by-level/{level}", response_model=PaginationResponse[CourseResponse])
async def get_courses_by_level(
    level: str = Path(..., description="Course level"),
    params: CommonQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """Get courses by level with pagination"""
    return await course_service.get_by_level(
        db=db, 
        level=level, 
        page=params.page, 
        limit=params.limit
    )

@router.get("/search", response_model=PaginationResponse[CourseResponse])
async def search_courses(
    q: str = Query(..., min_length=1, description="Search query"),
    params: CommonQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """Search courses with pagination"""
    return await course_service.search_courses(
        db=db, 
        search_query=q, 
        page=params.page, 
        limit=params.limit
    )