from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Any
from uuid import UUID

from app.core.database import get_db
from app.dependencies import get_current_user, CommonQueryParams
from app.schemas.notification import NotificationResponse
from app.repositories.notification import notification_repo
from app.services.notification_service import notification_service
from app.models.user import User

# Step 1: Import core components
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException

# Step 1: Khai báo Router với ResponseWrapperRoute
router = APIRouter(prefix="/notifications", tags=["Notifications"], route_class=ResponseWrapperRoute)

# ============================================================
# LIST NOTIFICATIONS
# ============================================================
@router.get("", response_model=PaginationResponse[NotificationResponse])
def get_my_notifications(
    params: CommonQueryParams = Depends(), 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lấy danh sách thông báo của user hiện tại"""
    noti = notification_repo.get_by_user(db, user_id=current_user.id, skip=params.skip, limit=params.limit)
    count = notification_repo.count_by_user(db, user_id=current_user.id)
    
    # Step 3: Xử lý Pagination
    return PaginationResponse(
        data=noti,
        total=count,
        page=params.page,
        limit=params.limit
    )

# ============================================================
# UNREAD COUNT & ACTIONS
# ============================================================
@router.get("/unread-count", response_model=ApiResponse[dict])
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Đếm số thông báo chưa đọc"""
    count = notification_repo.count_unread(db, user_id=current_user.id)
    return ApiResponse(data={"unread_count": count})

@router.put("/read-all", response_model=ApiResponse[Any])
async def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Mark ALL notifications as read for the current user"""
    result = await notification_service.mark_all_as_read(db, current_user.id)
    return ApiResponse(data=result)

@router.put("/{notification_id}/read", response_model=ApiResponse[NotificationResponse])
def mark_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Đánh dấu một thông báo là đã đọc"""
    noti = notification_service.mark_as_read(db, notification_id, current_user.id)
    
    if not noti:
        # Step 4: Thay thế Exception
        raise APIException(status_code=404, code="NOT_FOUND", message="Notification not found")
        
    return ApiResponse(data=noti)