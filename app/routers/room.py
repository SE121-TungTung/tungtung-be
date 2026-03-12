from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.dependencies import CommonQueryParams, get_current_admin_user
from app.models.academic import Room
from app.schemas.base_schema import PaginationResponse
from app.services.room_service import room_service
from app.routers.generator import create_crud_router
from app.schemas.room import RoomResponse

base_router = create_crud_router(
    model=Room,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user
)

# Main router
router = APIRouter(tags=["Rooms"])

# Include generated CRUD
router.include_router(base_router, prefix="")

# Add custom endpoints
@router.get("/available", response_model=PaginationResponse[RoomResponse])
async def get_available_rooms(
    params: CommonQueryParams = Depends(),
    min_capacity: Optional[int] = Query(None, description="Minimum capacity"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """Get available rooms with optional capacity filter"""
    
    # Truyền thẳng page và limit vào Service
    return await room_service.get_available_rooms(
        db=db, 
        min_capacity=min_capacity, 
        page=params.page, 
        limit=params.limit
    )