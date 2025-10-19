from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.dependencies import get_current_admin_user
from app.models.academic import Room
from app.services.room import room_service
from app.routers.generator import create_crud_router

# Generate base CRUD using your existing generator ✅
base_router = create_crud_router(
    model=Room,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user
)

# Main router
router = APIRouter(prefix="/rooms", tags=["Rooms"])

# Include generated CRUD
router.include_router(base_router, prefix="")

# Add custom endpoints
@router.get("/available")
async def get_available_rooms(
    min_capacity: int = Query(None, description="Minimum capacity"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """Get available rooms with optional capacity filter"""
    return await room_service.get_available_rooms(db, min_capacity)