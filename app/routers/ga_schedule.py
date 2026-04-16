"""
GA Schedule Router
==================
API endpoints for the Genetic Algorithm schedule optimizer.

All endpoints require admin authentication.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, status
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.core.route import ResponseWrapperRoute
from app.dependencies import get_current_admin_user, CommonQueryParams
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.schemas.ga_schedule import (
    GAApplyResponse,
    GARunDetailResponse,
    GARunResponse,
    GAScheduleRequest,
    TeacherUnavailabilityCreate,
    TeacherUnavailabilityResponse,
)
from app.services.schedule.ga_service import ga_schedule_service


router = APIRouter(
    prefix="/schedule/ga",
    tags=["GA Schedule Optimizer"],
    route_class=ResponseWrapperRoute,
)


# ============================================================
# GA RUN ENDPOINTS
# ============================================================

@router.post(
    "/run",
    response_model=ApiResponse[GARunResponse],
    status_code=status.HTTP_202_ACCEPTED,
    summary="Chạy GA tạo đề xuất TKB",
)
async def run_ga_schedule(
    request: GAScheduleRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Khởi chạy Genetic Algorithm để tối ưu hóa thời khóa biểu.

    - Trả về `run_id` ngay lập tức (HTTP 202).
    - GA chạy background. Poll `GET /runs/{run_id}` để xem kết quả.
    - Khi status = `completed`, call `POST /runs/{run_id}/apply` để áp dụng.
    """
    result = ga_schedule_service.run_ga_schedule(db, request)

    # Schedule GA execution as background task
    background_tasks.add_task(
        ga_schedule_service.execute_ga_background,
        run_id=result.run_id,
        request=request,
    )

    return ApiResponse(data=result, message="GA đã bắt đầu chạy. Dùng run_id để theo dõi kết quả.")


@router.get(
    "/runs",
    summary="Lịch sử các lần chạy GA",
)
async def get_ga_run_history(
    params: CommonQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Lấy danh sách các lần chạy GA với phân trang."""
    return ga_schedule_service.get_run_history(db, page=params.page, limit=params.limit)


@router.get(
    "/runs/{run_id}",
    response_model=ApiResponse[GARunDetailResponse],
    summary="Chi tiết kết quả GA run",
)
async def get_ga_run_detail(
    run_id: UUID = Path(..., description="ID của GA run"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Lấy chi tiết kết quả của một lần chạy GA.

    Bao gồm:
    - Danh sách tất cả sessions đề xuất
    - Các xung đột (nếu có)
    - Thống kê và cấu hình GA
    """
    result = ga_schedule_service.get_run_result(db, run_id)
    return ApiResponse(data=result)


@router.post(
    "/runs/{run_id}/apply",
    response_model=ApiResponse[GAApplyResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Confirm & apply GA proposal",
)
async def apply_ga_proposal(
    run_id: UUID = Path(..., description="ID của GA run cần apply"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Admin xác nhận và áp dụng đề xuất GA vào lịch học thực tế.

    - Kiểm tra không còn hard constraint violations
    - Tạo ClassSession records từ proposals
    - Gửi notification tới giáo viên & học viên
    - Cập nhật GA run status → `applied`
    """
    result = ga_schedule_service.apply_ga_proposal(db, run_id)
    return ApiResponse(data=result)


@router.delete(
    "/runs/{run_id}",
    response_model=ApiResponse[Dict[str, Any]],
    summary="Xóa GA run",
)
async def delete_ga_run(
    run_id: UUID = Path(..., description="ID của GA run cần xóa"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Soft delete GA run và tất cả proposals liên quan."""
    result = ga_schedule_service.delete_run(db, run_id)
    return ApiResponse(data=result)


# ============================================================
# TEACHER UNAVAILABILITY ENDPOINTS
# ============================================================

@router.post(
    "/teacher-unavailability",
    response_model=ApiResponse[TeacherUnavailabilityResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Thêm lịch bận giáo viên",
)
async def create_teacher_unavailability(
    data: TeacherUnavailabilityCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    Thêm lịch bận cho giáo viên (input cho GA).

    Hỗ trợ:
    - Ngày cụ thể (`is_recurring=false`, `unavailable_date` bắt buộc)
    - Lặp hàng tuần (`is_recurring=true`, `day_of_week` bắt buộc)
    - Tiết cụ thể (`time_slots`) hoặc cả ngày (để `time_slots=null`)
    """
    result = ga_schedule_service.create_teacher_unavailability(db, data)
    return ApiResponse(data=result)


@router.get(
    "/teacher-unavailability",
    summary="Xem lịch bận giáo viên",
)
async def get_teacher_unavailability(
    teacher_id: Optional[UUID] = Query(None, description="Lọc theo teacher_id"),
    params: CommonQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Lấy danh sách lịch bận giáo viên với phân trang."""
    return ga_schedule_service.get_teacher_unavailability(
        db, teacher_id=teacher_id, page=params.page, limit=params.limit,
    )


@router.delete(
    "/teacher-unavailability/{record_id}",
    response_model=ApiResponse[Dict[str, Any]],
    summary="Xóa lịch bận giáo viên",
)
async def delete_teacher_unavailability(
    record_id: UUID = Path(..., description="ID của record lịch bận"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Soft delete lịch bận giáo viên."""
    result = ga_schedule_service.delete_teacher_unavailability(db, record_id)
    return ApiResponse(data=result)
