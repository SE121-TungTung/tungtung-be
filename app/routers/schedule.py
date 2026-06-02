from fastapi import APIRouter, Depends, Path, Query, BackgroundTasks, status
from datetime import date
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.dependencies import get_current_admin_user, get_current_active_user, get_current_week_range
from app.services.schedule_service import schedule_service
from app.schemas.schedule import (
    ScheduleGenerateRequest, 
    ScheduleProposal, 
    SessionCreate, 
    SessionUpdate, 
    SessionResponse, 
    WeeklySchedule
)

# Step 1: Import core components
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse
from app.core.exceptions import APIException

# Step 1: Khai báo Router với ResponseWrapperRoute
router = APIRouter(prefix="/schedule", tags=["Schedule Management"], route_class=ResponseWrapperRoute)

# ============================================================
# SCHEDULE GENERATION & APPLY
# ============================================================

@router.post("/generate", response_model=ApiResponse[ScheduleProposal])
async def generate_schedule_proposal(
    request: ScheduleGenerateRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    UC MF.3: Auto-schedule. 
    Generate schedule proposal để admin review (Hard Constraints check).
    """
    result = schedule_service.generate_schedule(db, request)
    return ApiResponse(data=result)

@router.post("/apply", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[Dict[str, Any]])
async def apply_schedule_proposal(
    proposal: ScheduleProposal,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    UC MF.5: Admin confirm và apply proposal. 
    Thực hiện lưu Session và Trigger Notifications.
    """
    result = schedule_service.apply_proposal(db, proposal)
    return ApiResponse(data=result)

# ============================================================
# MANUAL SESSION MANAGEMENT
# ============================================================

@router.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[SessionResponse])
async def create_session(
    data: SessionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """UC MF.3.1: Tạo session thủ công với Conflict Check"""
    result = await schedule_service.create_session_manual(db, data, background_tasks)
    return ApiResponse(data=result)

@router.put("/sessions/{session_id}", response_model=ApiResponse[SessionResponse])
async def update_session(
    data: SessionUpdate,
    session_id: UUID = Path(..., description="ID của Session cần cập nhật"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """UC MF.3.3: Update session với Conflict Check"""
    result = schedule_service.update_session(db, session_id, data)
    return ApiResponse(data=result)

@router.delete("/sessions/{session_id}", response_model=ApiResponse[Dict[str, Any]])
async def delete_session(
    session_id: UUID = Path(..., description="ID của Session cần hủy"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """UC MF.3.4: Cancel/Soft Delete session"""
    result = schedule_service.delete_session(db, session_id)
    return ApiResponse(data=result)

# ============================================================
# SCHEDULE VIEWING
# ============================================================

@router.get("/weekly", tags=["Schedule Viewing"], response_model=ApiResponse[WeeklySchedule])
async def get_weekly_schedule_view(
    start_date: Optional[date] = Query(None, description="Ngày bắt đầu của tuần (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Ngày kết thúc của tuần (YYYY-MM-DD)"),
    class_id: Optional[UUID] = Query(None, description="Lọc theo ID lớp học"),
    user_id: Optional[UUID] = Query(None, description="Lọc theo ID người dùng (Giáo viên)"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """
    Lấy thời khóa biểu chi tiết dạng tuần, có thể lọc theo lớp hoặc giáo viên.
    """
    if not (start_date and end_date):
        start_date, end_date = get_current_week_range()
        
    result = schedule_service.get_weekly_schedule(
        db, start_date, end_date, class_id=class_id, user_id=user_id
    )
    return ApiResponse(data=result)