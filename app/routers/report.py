"""
Report Router
GET    /api/v1/reports/revenue      - Báo cáo doanh thu (filter ngày, nhóm khóa học)
GET    /api/v1/reports/expenses     - Báo cáo chi phí (filter loại chi phí, lương)
GET    /api/v1/reports/profit       - Báo cáo lợi nhuận tổng hợp
GET    /api/v1/reports/debts        - Danh sách học viên nợ phí / chưa hoàn tất TT
POST   /api/v1/reports/export-jobs  - Khởi tạo tiến trình xuất file báo cáo (async)

Tất cả report endpoints yêu cầu quyền tối thiểu OFFICE_ADMIN.
Các endpoint GET trả về dữ liệu tổng hợp real-time (hoặc cache ngắn hạn).
export-jobs chạy bất đồng bộ — client cần polling job_id hoặc nhận webhook.
"""
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.core.database import get_db
from app.dependencies import require_any_role
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.models.user import User, UserRole
from app.models.finance import ReportType

from app.schemas.finance.report import (
    RevenueReportResponse,
    ExpensesReportResponse,
    ProfitReportResponse,
    DebtListResponse,
    ExportJobCreate,
    ExportJobResponse,
)

from app.services.finance.report_service import report_service

router = APIRouter(prefix="/reports", tags=["Reports"])


# ---------------------------------------------------------------------------
# GET /reports/revenue
# Báo cáo doanh thu theo khoảng thời gian, có thể group theo khóa học.
# ---------------------------------------------------------------------------
# report_service cần implement:
#   - report_service.get_revenue_report(db, date_from, date_to, group_by_course)
#       -> RevenueReportResponse
#       + Aggregate payments SUCCESS trong khoảng thời gian
#       + Nếu group_by_course=True: breakdown theo từng course/class
#       + Tính: total_revenue, total_invoices, avg_payment_value
#       + Có thể cache ngắn hạn (5-10 phút) để tránh query nặng
# ---------------------------------------------------------------------------
@router.get("/revenue", response_model=ApiResponse[RevenueReportResponse])
async def get_revenue_report(
    date_from: Optional[date] = Query(None, description="Từ ngày (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="Đến ngày (YYYY-MM-DD)"),
    group_by_course: bool = Query(False, description="Nhóm theo khóa học"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN)),
):
    result = report_service.get_revenue_report(
        db=db,
        date_from=date_from,
        date_to=date_to,
        group_by_course=group_by_course,
    )
    return ApiResponse(success=True, data=result, message="Thành công")


# ---------------------------------------------------------------------------
# GET /reports/expenses
# Báo cáo chi phí: lương giáo viên, vận hành, v.v.
# ---------------------------------------------------------------------------
# report_service cần implement:
#   - report_service.get_expenses_report(db, date_from, date_to, cost_type)
#       -> ExpensesReportResponse
#       + cost_type: SALARY | OPERATIONS | ALL
#       + Tổng hợp từ salary records (module KPI/Payroll) và expense records
#       + Breakdown theo category
# ---------------------------------------------------------------------------
@router.get("/expenses", response_model=ApiResponse[ExpensesReportResponse])
async def get_expenses_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    cost_type: Optional[str] = Query(None, description="SALARY | OPERATIONS | ALL"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN)),
):
    result = report_service.get_expenses_report(
        db=db,
        date_from=date_from,
        date_to=date_to,
        cost_type=cost_type,
    )
    return ApiResponse(success=True, data=result, message="Thành công")


# ---------------------------------------------------------------------------
# GET /reports/profit
# Báo cáo lợi nhuận tổng hợp = Doanh thu - Chi phí.
# ---------------------------------------------------------------------------
# report_service cần implement:
#   - report_service.get_profit_report(db, date_from, date_to) -> ProfitReportResponse
#       + Tổng hợp revenue + expenses trong cùng khoảng thời gian
#       + profit = total_revenue - total_expenses
#       + profit_margin = profit / total_revenue * 100
#       + Month-over-month trend nếu range > 1 tháng
# ---------------------------------------------------------------------------
@router.get("/profit", response_model=ApiResponse[ProfitReportResponse])
async def get_profit_report(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN)),
):
    result = report_service.get_profit_report(
        db=db,
        date_from=date_from,
        date_to=date_to,
    )
    return ApiResponse(success=True, data=result, message="Thành công")


# ---------------------------------------------------------------------------
# GET /reports/debts
# Danh sách học viên nợ phí hoặc có invoice PENDING quá hạn.
# ---------------------------------------------------------------------------
# report_service cần implement:
#   - report_service.get_debt_report(db, page, limit) -> Tuple[List[DebtListResponse], int]
#       + Query Invoice status=PENDING mà due_date < now()
#       + Join với users để lấy thông tin học viên
#       + Tính số ngày quá hạn
#       + Sắp xếp theo số tiền nợ desc
# ---------------------------------------------------------------------------
@router.get("/debts", response_model=PaginationResponse[DebtListResponse])
async def get_debt_report(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN)),
):
    import math
    items, total = report_service.get_debt_report(db=db, page=page, limit=limit)
    meta = PaginationMetadata(
        page=page, limit=limit, total=total,
        total_pages=math.ceil(total / limit) if limit else 0,
    )
    return PaginationResponse(success=True, data=items, meta=meta, message="Thành công")


# ---------------------------------------------------------------------------
# POST /reports/export-jobs
# Khởi tạo job xuất file báo cáo bất đồng bộ (CSV / Excel / PDF).
# Client nhận job_id → polling GET /reports/export-jobs/{job_id} (nếu implement)
# hoặc nhận webhook khi hoàn tất.
# ---------------------------------------------------------------------------
# report_service cần implement:
#   - report_service.create_export_job(db, payload, created_by, bg_tasks)
#       -> ExportJobResponse
#       + Persist ReportExportJob với status=PENDING
#       + Enqueue background task (bg_tasks.add_task hoặc Celery)
#       + Background task:
#           - Query dữ liệu theo report_type + filters
#           - Generate file (openpyxl / reportlab)
#           - Upload lên S3/GCS
#           - Update job: status=COMPLETED, file_url=presigned_url
#           - Nếu lỗi: status=FAILED, error_message=...
# ---------------------------------------------------------------------------
@router.post("/export-jobs", response_model=ApiResponse[ExportJobResponse])
async def create_export_job(
    payload: ExportJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN)),
):
    result = report_service.create_export_job(
        db=db,
        payload=payload,
        created_by=current_user.id,
        bg_tasks=background_tasks,
    )
    return ApiResponse(
        success=True,
        data=result,
        message="Đã khởi tạo tiến trình xuất báo cáo. Vui lòng chờ hoàn tất.",
    )