from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional

from app.core.database import get_db
from app.services.attendance_service import attendance_service
from app.schemas.attendance import (
    BatchAttendanceRequest, AttendanceResponseItem,
    StudentCheckInRequest, StudentCheckInResponse,
    BatchNoteUpdateRequest, QRTokenResponse,
    StudentAttendanceStats, ClassAttendanceStats, AbsentAlertItem,
    CertificateEligibilityResponse,
    AttendanceConfigResponse, AttendanceConfigUpdate,
)
from app.models.user import UserRole
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse
from app.core.exceptions import APIException
from app.dependencies import get_current_user, get_current_admin_user, get_current_teacher_or_admin


# ============================================================
# ROUTER 1: Session-scoped (/sessions/{session_id}/attendance)
# ============================================================
session_router = APIRouter(
    prefix="/sessions/{session_id}/attendance",
    tags=["Attendance"],
    route_class=ResponseWrapperRoute,
)


@session_router.get("", response_model=ApiResponse[List[AttendanceResponseItem]])
def get_attendance_sheet(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Lấy bảng điểm danh của buổi học."""
    return attendance_service.get_session_attendance_sheet(db=db, session_id=session_id)


@session_router.put("", response_model=ApiResponse[dict])
def mark_attendance(
    session_id: UUID,
    payload: BatchAttendanceRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher_or_admin),
):
    """
    Điểm danh hàng loạt.
    CHỈ cho phép khi session đang SCHEDULED hoặc IN_PROGRESS.
    """
    return attendance_service.bulk_mark_attendance(
        db=db,
        session_id=session_id,
        data=payload,
        marker_id=current_user.id,
    )


@session_router.patch("/notes", response_model=ApiResponse[dict])
def update_attendance_notes(
    session_id: UUID,
    payload: BatchNoteUpdateRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher_or_admin),
):
    """
    Cập nhật ghi chú lý do cho attendance records.
    Cho phép ở MỌI trạng thái session (kể cả COMPLETED).
    Chỉ cập nhật notes, KHÔNG thay đổi status.
    """
    return attendance_service.update_attendance_notes(
        db=db,
        session_id=session_id,
        data=payload,
        marker_id=current_user.id,
    )


@session_router.post("/qr", response_model=ApiResponse[QRTokenResponse])
def generate_qr_token(
    session_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher_or_admin),
):
    """Tạo QR token cho buổi học. Chỉ giáo viên của buổi học mới được tạo."""
    return attendance_service.generate_qr_token(
        db=db,
        session_id=session_id,
        teacher_id=current_user.id,
    )


@session_router.post("/self-check-in", response_model=ApiResponse[StudentCheckInResponse])
def student_self_check_in(
    session_id: UUID,
    payload: StudentCheckInRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Học viên tự điểm danh (bằng session_id hoặc quét mã QR).
    """
    if current_user.role != UserRole.STUDENT:
        raise APIException(
            status_code=403,
            code="FORBIDDEN",
            message="Chỉ học viên mới có thể tự điểm danh",
        )

    result = attendance_service.process_student_self_check_in(
        db=db,
        student_id=current_user.id,
        session_id=payload.session_id or session_id,
        qr_token=payload.qr_token,
    )
    return result


# ============================================================
# ROUTER 2: Class-scoped (/classes/{class_id}/attendance)
# ============================================================
class_router = APIRouter(
    prefix="/classes/{class_id}/attendance",
    tags=["Attendance"],
    route_class=ResponseWrapperRoute,
)


@class_router.get("/stats", response_model=ApiResponse[ClassAttendanceStats])
def get_class_attendance_stats(
    class_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher_or_admin),
):
    """Thống kê tổng hợp điểm danh cho 1 lớp."""
    return attendance_service.get_class_attendance_stats(db=db, class_id=class_id)


@class_router.get("/students", response_model=ApiResponse[List[StudentAttendanceStats]])
def get_student_attendance_stats(
    class_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher_or_admin),
):
    """Thống kê điểm danh từng học viên trong 1 lớp."""
    return attendance_service.get_student_attendance_stats(db=db, class_id=class_id)


# ============================================================
# ROUTER 3: Global attendance (/attendance)
# ============================================================
global_router = APIRouter(
    prefix="/attendance",
    tags=["Attendance"],
    route_class=ResponseWrapperRoute,
)


@global_router.get("/alerts", response_model=ApiResponse[List[AbsentAlertItem]])
def get_absent_alerts(
    class_id: Optional[UUID] = Query(None, description="Lọc theo lớp (tuỳ chọn)"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Danh sách học viên vắng nhiều. Chỉ Admin."""
    return attendance_service.get_absent_alerts(db=db, class_id=class_id)


@global_router.get("/config", response_model=ApiResponse[AttendanceConfigResponse])
def get_attendance_config(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Lấy cấu hình điểm danh."""
    return attendance_service.get_attendance_config(db=db)


@global_router.put("/config", response_model=ApiResponse[AttendanceConfigResponse])
def update_attendance_config(
    payload: AttendanceConfigUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Cập nhật cấu hình điểm danh. Chỉ Admin."""
    return attendance_service.update_attendance_config(db=db, data=payload)


# ============================================================
# ROUTER 4: Enrollment-scoped (/enrollments/{enrollment_id})
# ============================================================
enrollment_router = APIRouter(
    prefix="/enrollments/{enrollment_id}",
    tags=["Attendance"],
    route_class=ResponseWrapperRoute,
)


@enrollment_router.get(
    "/certificate-eligibility",
    response_model=ApiResponse[CertificateEligibilityResponse],
)
def check_certificate_eligibility(
    enrollment_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Kiểm tra học viên có đủ điều kiện nhận chứng chỉ ảo không.
    Student chỉ xem được của mình. Teacher/Admin xem được tất cả.
    """
    # Permission check: student chỉ xem enrollment của mình
    if current_user.role == UserRole.STUDENT:
        from app.models.academic import ClassEnrollment
        enrollment = db.query(ClassEnrollment).filter(
            ClassEnrollment.id == enrollment_id
        ).first()
        if not enrollment or enrollment.student_id != current_user.id:
            raise APIException(
                status_code=403,
                code="FORBIDDEN",
                message="Bạn không có quyền xem thông tin này",
            )

    return attendance_service.check_certificate_eligibility(
        db=db, enrollment_id=enrollment_id
    )


# ============================================================
# COMBINED ROUTER (include tất cả vào 1 router export)
# ============================================================
router = APIRouter()
router.include_router(session_router)
router.include_router(class_router)
router.include_router(global_router)
router.include_router(enrollment_router)