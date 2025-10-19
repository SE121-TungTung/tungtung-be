from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.dependencies import get_current_admin_user
from app.models.academic import Course
from app.services.course import course_service
from app.routers.generator import create_crud_router

# Generate base CRUD
base_router = create_crud_router(
    model=Course,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user
)

# Main router
router = APIRouter(prefix="/courses", tags=["Courses"])
router.include_router(base_router, prefix="")

# Custom endpoints
@router.get("/active")
async def get_active_courses(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """Get all active courses"""
    return await course_service.get_active_courses(db)

@router.get("/by-level/{level}")
async def get_courses_by_level(
    level: str = Path(..., description="Course level"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """Get courses by level"""
    return await course_service.get_by_level(db, level)

@router.get("/search")
async def search_courses(
    q: str = Query(..., min_length=1, description="Search query"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """Search courses"""
    return await course_service.search_courses(db, q)