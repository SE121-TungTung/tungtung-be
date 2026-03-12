from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from app.core.database import get_db
from app.services.attendance_service import attendance_service
from app.schemas.attendance import BatchAttendanceRequest, AttendanceResponseItem, StudentCheckInRequest, StudentCheckInResponse
from app.models.user import UserRole
# Step 1 & 3: Import core components và CommonQueryParams
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException
from app.dependencies import get_current_user, CommonQueryParams

# Step 1: Khai báo Router với ResponseWrapperRoute
router = APIRouter(prefix="/sessions/{session_id}/attendance", tags=["Attendance"], route_class=ResponseWrapperRoute)

# ============================================================
# GET ATTENDANCE SHEET (LIST)
# ============================================================
@router.get("", response_model=ApiResponse[List[AttendanceResponseItem]])
def get_attendance_sheet(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # TODO: Thêm check permission (User có phải giáo viên lớp này không?)
    return attendance_service.get_session_attendance_sheet(
        db=db, 
        session_id=session_id
    )

# ============================================================
# MARK ATTENDANCE (BATCH UPDATE)
# ============================================================
@router.put("", response_model=ApiResponse[List[AttendanceResponseItem]])
def mark_attendance(
    session_id: UUID,
    payload: BatchAttendanceRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # TODO: Thêm check permission (Chỉ GV hoặc Admin được điểm danh)
    result = attendance_service.bulk_mark_attendance(
        db=db, 
        session_id=session_id, 
        payload=payload, 
        marker_id=current_user.id
    )
    return ApiResponse(data=result)

# ============================================================
# STUDENT SELF CHECK-IN
# ============================================================
@router.post("/self-check-in", response_model=ApiResponse[StudentCheckInResponse])
def student_self_check_in(
    payload: StudentCheckInRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # Step 4: Thay thế Exception
    if current_user.role != UserRole.STUDENT:
        raise APIException(
            status_code=403, 
            code="FORBIDDEN", 
            message="Only students can perform self check-in"
        )

    result = attendance_service.process_student_self_check_in(
        db=db, 
        user_id=current_user.id, 
        session_id=payload.session_id
    )
    
    return ApiResponse(data=result)