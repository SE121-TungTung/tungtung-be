# app/routers/notification.py
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Any
from uuid import UUID

from app.core.database import get_db
from app.dependencies import get_current_user
from app.schemas.notification import NotificationResponse
from app.repositories.notification import notification_repo
from app.services.notification import notification_service
from app.models.user import User

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.get("/", response_model=List[NotificationResponse])
def get_my_notifications(
    skip: int = 0, 
    limit: int = 50, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lấy danh sách thông báo của user hiện tại"""
    return notification_repo.get_by_user(db, user_id=current_user.id, skip=skip, limit=limit)

@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Đếm số thông báo chưa đọc"""
    count = notification_repo.count_unread(db, user_id=current_user.id)
    return {"unread_count": count}

@router.put("/{notification_id}/read", response_model=NotificationResponse)
def mark_notification_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Đánh dấu một thông báo là đã đọc"""
    noti = notification_service.mark_as_read(db, notification_id, current_user.id)
    if not noti:
        raise HTTPException(status_code=404, detail="Notification not found")
    return noti