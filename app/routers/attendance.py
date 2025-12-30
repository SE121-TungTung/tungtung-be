from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
from fastapi import HTTPException

from app.core.database import get_db
from app.services.attendance import attendance_service
from app.schemas.attendance import BatchAttendanceRequest, AttendanceResponseItem, StudentCheckInRequest, StudentCheckInResponse
from app.models.user import UserRole
from app.core.security import get_current_user # Giả sử bạn có auth

router = APIRouter(prefix="/sessions/{session_id}/attendance", tags=["Attendance"])

@router.get("/", response_model=List[AttendanceResponseItem])
def get_attendance_sheet(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # TODO: Thêm check permission (User có phải giáo viên lớp này không?)
    return attendance_service.get_session_attendance_sheet(db, session_id)

@router.put("/", status_code=status.HTTP_200_OK)
def mark_attendance(
    session_id: UUID,
    payload: BatchAttendanceRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    # TODO: Thêm check permission (Chỉ GV hoặc Admin được điểm danh)
    return attendance_service.bulk_mark_attendance(
        db, 
        session_id, 
        payload, 
        marker_id=current_user.id
    )

@router.post("/self-check-in", response_model=StudentCheckInResponse)
def student_self_check_in(
    payload: StudentCheckInRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user) # Bắt buộc phải là role STUDENT
):
    # Kiểm tra role (nếu middleware chưa chặn)
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(403, "Only students can perform self check-in")

    result = attendance_service.process_student_self_check_in(
        db, 
        current_user.id, 
        payload.session_id
    )
    
    return result