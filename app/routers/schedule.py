# app/api/v1/endpoints/schedule.py

from fastapi import APIRouter, Depends, status, Path, Query, BackgroundTasks
from datetime import date
from typing import Optional
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies import get_current_admin_user, get_current_week_range
from app.services.schedule import schedule_service
from app.schemas.schedule import ScheduleGenerateRequest, ScheduleProposal, SessionCreate, SessionUpdate, SessionResponse, WeeklySchedule
from uuid import UUID
from typing import Dict, Any

router = APIRouter(prefix="/schedule", tags=["Schedule Management"])

@router.post("/generate", response_model=ScheduleProposal)
async def generate_schedule_proposal(
    request: ScheduleGenerateRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    UC MF.3: Auto-schedule. 
    Generate schedule proposal để admin review (Hard Constraints check).
    """
    # LƯU Ý: Phải có instance schedule_service được định nghĩa bên ngoài
    return schedule_service.generate_schedule(db, request)

@router.post("/apply", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def apply_schedule_proposal(
    proposal: ScheduleProposal,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    UC MF.5: Admin confirm và apply proposal. 
    Thực hiện lưu Session và Trigger Notifications.
    """
    return schedule_service.apply_proposal(db, proposal)

@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: SessionCreate,
    background_tasks: BackgroundTasks, # Inject BackgroundTasks
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """UC MF.3.1: Tạo session thủ công với Conflict Check"""
    # Truyền background_tasks vào service
    return await schedule_service.create_session_manual(db, data, background_tasks)

@router.get("/weekly", response_model=WeeklySchedule, tags=["Schedule Viewing"])
async def get_weekly_schedule_view(
    start_date: Optional[date] = Query(None, description="Ngày bắt đầu của tuần (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Ngày kết thúc của tuần (YYYY-MM-DD)"),
    class_id: Optional[UUID] = Query(None, description="Lọc theo ID lớp học"),
    db: Session = Depends(get_db),
    # Cho phép xem TKBiểu cá nhân
    user_id: Optional[UUID] = Query(None, description="Lọc theo ID người dùng (Giáo viên)"),
):
    """
    Lấy thời khóa biểu chi tiết dạng tuần, có thể lọc theo lớp hoặc giáo viên.
    """
    # Nếu user_id không được cung cấp, sử dụng ID của người dùng hiện tại (nếu cần)
    if not (start_date and end_date):
        start_date, end_date = get_current_week_range()
    return schedule_service.get_weekly_schedule(
        db, start_date, end_date, class_id=class_id, user_id=user_id
    )

@router.put("/sessions/{session_id}", response_model=SessionResponse)
async def update_session(
    data: SessionUpdate,
    session_id: UUID = Path(..., description="ID của Session cần cập nhật"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """UC MF.3.3: Update session với Conflict Check"""
    return schedule_service.update_session(db, session_id, data)

@router.delete("/sessions/{session_id}", response_model=Dict[str, Any])
async def delete_session(
    session_id: UUID = Path(..., description="ID của Session cần hủy"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """UC MF.3.4: Cancel/Soft Delete session"""
    return schedule_service.delete_session(db, session_id)

# END OF app/api/v1/endpoints/schedule.py