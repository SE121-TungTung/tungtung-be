"""
KPI & Payroll Router — Lotus KPI Module

Endpoints organized by:
1. Templates (System Admin)
2. Periods (Center Admin+)
3. Records (Office Admin+ / Self-view for Teachers)
4. Support Calculator (Office Admin+)
5. Dashboard & Reports (Center Admin+)
6. Disputes (Teachers / Center Admin+)
7. Payroll (kept from old system)
"""

from fastapi import APIRouter, Depends, Query, Path, Body, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import math

from app.core.database import get_db
from app.dependencies import (
    get_current_user, require_role, get_current_admin_user,
    get_current_teacher_or_admin, require_any_role,
)
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.models.user import User, UserRole
from app.models.kpi import ApprovalStatus

from app.schemas.kpi import (
    # Template
    KPITemplateCreate, KPITemplateUpdate, KPITemplateResponse,
    KPITemplateListResponse, KPITemplateMetricResponse,
    # Period
    KPIPeriodCreate, KPIPeriodResponse, KPIPeriodDetailResponse,
    # Record
    KPIRecordListItem, KPIRecordDetailResponse, UpdateMetricsRequest,
    UpdateTeachingHoursRequest, MetricResultResponse,
    # Support Calc
    SupportCalcRequest, SupportCalcResponse, SupportCalcSaveRequest,
    SupportCalcEntryResponse,
    # Approval
    KPIApprovalLogResponse, RejectRequest,
    # Dashboard
    KPIDashboardSummary, KPIRankingItem, StaffKPIHistoryItem,
    # Dispute
    KpiDisputeCreate, KpiDisputeResponse, KpiDisputeResolveRequest,
    # Payroll (kept)
    KpiTierResponse, KpiTierUpdate,
    TeacherPayrollConfigUpdate, TeacherPayrollConfigResponse,
    SalaryResponse, SalaryAdjustmentCreate, SalaryAdjustmentResponse,
    PayrollRunCreate, PayrollRunResponse,
    # Deprecated (kept for compat)
    KpiCalculationJobCreate, KpiCalculationJobResponse,
    TeacherMonthlyKpiResponse, KpiRawMetricSync,
    KpiSummaryItem, KpiSummaryPeriodMeta, PERIOD_REGEX,
)

from app.services.kpi.template_service import kpi_template_service
from app.services.kpi.period_service import kpi_period_service
from app.services.kpi.record_service import kpi_record_service
from app.services.kpi.calculation_service import kpi_calculation_service
from app.services.kpi.support_calc_service import support_calc_service
from app.services.kpi.dashboard_service import kpi_dashboard_service
from app.services.kpi.dispute_service import kpi_dispute_service
from app.services.kpi.settings_service import kpi_settings_service
from app.services.kpi.payroll_service import salary_service, teacher_payroll_config_service, payroll_run_service

router = APIRouter(prefix="", tags=["KPI & Payroll"])

# Shorthand for role dependencies
AdminOnly = Depends(require_role(UserRole.SYSTEM_ADMIN))
CenterAdminUp = Depends(require_any_role(UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN))
OfficeAdminUp = Depends(require_any_role(
    UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN
))
TeacherOrAdmin = Depends(get_current_teacher_or_admin)

PeriodQuery = Optional[str]


# ===========================================================================
# 1. KPI Templates
# ===========================================================================

@router.get("/kpi/templates", response_model=ApiResponse[List[KPITemplateListResponse]])
async def list_templates(
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    templates = kpi_template_service.list_templates(db)
    return ApiResponse(success=True, data=templates, message="Thành công")


@router.get("/kpi/templates/{template_id}", response_model=ApiResponse[KPITemplateResponse])
async def get_template(
    template_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    template = kpi_template_service.get_template(db, template_id)
    return ApiResponse(success=True, data=template, message="Thành công")


@router.post("/kpi/templates", response_model=ApiResponse[KPITemplateResponse])
async def create_template(
    payload: KPITemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = AdminOnly,
):
    template = kpi_template_service.create_template(db, payload, current_user.id)
    return ApiResponse(success=True, data=template, message="Tạo template thành công")


@router.put("/kpi/templates/{template_id}", response_model=ApiResponse[KPITemplateResponse])
async def update_template(
    payload: KPITemplateUpdate,
    template_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = AdminOnly,
):
    template = kpi_template_service.update_template(db, template_id, payload)
    return ApiResponse(success=True, data=template, message="Cập nhật template thành công")


@router.get(
    "/kpi/templates/{template_id}/metrics",
    response_model=ApiResponse[List[KPITemplateMetricResponse]],
)
async def get_template_metrics(
    template_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    metrics = kpi_template_service.get_metrics(db, template_id)
    return ApiResponse(success=True, data=metrics, message="Thành công")


# ===========================================================================
# 2. KPI Periods
# ===========================================================================

@router.get("/kpi/periods", response_model=ApiResponse[List[KPIPeriodResponse]])
async def list_periods(
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    periods = kpi_period_service.list_periods(db)
    return ApiResponse(success=True, data=periods, message="Thành công")


@router.post("/kpi/periods", response_model=ApiResponse)
async def create_period(
    payload: KPIPeriodCreate,
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    result = kpi_period_service.create_period(db, payload, current_user.id)
    return ApiResponse(
        success=True,
        data={
            "period": KPIPeriodResponse.model_validate(result["period"]),
            "records_created": result["records_created"],
            "skipped": result["skipped"],
        },
        message=f"Tạo kỳ KPI thành công, đã tạo {result['records_created']} bản ghi",
    )


@router.get("/kpi/periods/{period_id}", response_model=ApiResponse[KPIPeriodDetailResponse])
async def get_period_detail(
    period_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    detail = kpi_period_service.get_period_detail(db, period_id)
    return ApiResponse(success=True, data=detail, message="Thành công")


@router.put("/kpi/periods/{period_id}/close", response_model=ApiResponse[KPIPeriodResponse])
async def close_period(
    period_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    period = kpi_period_service.close_period(db, period_id)
    return ApiResponse(success=True, data=period, message="Đóng kỳ KPI thành công")


# ===========================================================================
# 3. KPI Records
# ===========================================================================

@router.get("/kpi/records", response_model=PaginationResponse[KPIRecordListItem])
async def list_records(
    period_id: Optional[UUID] = Query(None),
    staff_id: Optional[UUID] = Query(None),
    status: Optional[ApprovalStatus] = Query(None),
    contract_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = OfficeAdminUp,
):
    items, total = kpi_record_service.list_records(
        db, period_id, staff_id, status, contract_type, page, limit
    )
    meta = PaginationMetadata(
        page=page, limit=limit, total=total,
        total_pages=math.ceil(total / limit) if limit else 0,
    )
    return PaginationResponse(success=True, data=items, meta=meta, message="Thành công")


@router.get("/kpi/records/me", response_model=ApiResponse[KPIRecordDetailResponse])
async def get_my_kpi_record(
    period_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detail = kpi_record_service.get_my_record(db, current_user.id, period_id)
    return ApiResponse(success=True, data=detail, message="Thành công")


@router.get("/kpi/records/{record_id}", response_model=ApiResponse[KPIRecordDetailResponse])
async def get_record_detail(
    record_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detail = kpi_record_service.get_record_detail(db, record_id)

    # Auth check: admin or owner
    is_admin = current_user.role in (
        UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN
    )
    if not is_admin and str(detail["staff_id"]) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Không có quyền xem KPI của người khác")

    return ApiResponse(success=True, data=detail, message="Thành công")


@router.put("/kpi/records/{record_id}/metrics", response_model=ApiResponse[KPIRecordDetailResponse])
async def update_record_metrics(
    payload: UpdateMetricsRequest,
    record_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = OfficeAdminUp,
):
    kpi_record_service.update_metrics(db, record_id, payload)
    detail = kpi_record_service.get_record_detail(db, record_id)
    return ApiResponse(success=True, data=detail, message="Cập nhật dữ liệu KPI thành công")


@router.put(
    "/kpi/records/{record_id}/teaching-hours",
    response_model=ApiResponse[KPIRecordDetailResponse],
)
async def update_teaching_hours(
    payload: UpdateTeachingHoursRequest,
    record_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = OfficeAdminUp,
):
    kpi_record_service.update_teaching_hours(db, record_id, payload.teaching_hours)
    detail = kpi_record_service.get_record_detail(db, record_id)
    return ApiResponse(success=True, data=detail, message="Cập nhật số giờ dạy thành công")


@router.post("/kpi/records/{record_id}/calculate", response_model=ApiResponse[KPIRecordDetailResponse])
async def calculate_record(
    record_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = OfficeAdminUp,
):
    kpi_calculation_service.calculate_record(db, record_id)
    detail = kpi_record_service.get_record_detail(db, record_id)
    return ApiResponse(success=True, data=detail, message="Tính toán KPI thành công")


@router.post("/kpi/records/{record_id}/submit", response_model=ApiResponse[KPIRecordDetailResponse])
async def submit_record(
    record_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = OfficeAdminUp,
):
    kpi_record_service.submit_record(db, record_id, current_user.id)
    detail = kpi_record_service.get_record_detail(db, record_id)
    return ApiResponse(success=True, data=detail, message="Submit KPI thành công")


@router.post("/kpi/records/{record_id}/approve", response_model=ApiResponse[KPIRecordDetailResponse])
async def approve_record(
    record_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    kpi_record_service.approve_record(db, record_id, current_user.id)
    detail = kpi_record_service.get_record_detail(db, record_id)
    return ApiResponse(success=True, data=detail, message="Duyệt KPI thành công")


@router.post("/kpi/records/{record_id}/reject", response_model=ApiResponse[KPIRecordDetailResponse])
async def reject_record(
    payload: RejectRequest,
    record_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    kpi_record_service.reject_record(db, record_id, current_user.id, payload.comment)
    detail = kpi_record_service.get_record_detail(db, record_id)
    return ApiResponse(success=True, data=detail, message="Từ chối KPI thành công")


@router.get(
    "/kpi/records/{record_id}/approval-log",
    response_model=ApiResponse[List[KPIApprovalLogResponse]],
)
async def get_approval_log(
    record_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = OfficeAdminUp,
):
    logs = kpi_record_service.get_approval_log(db, record_id)
    return ApiResponse(success=True, data=logs, message="Thành công")


# ===========================================================================
# 4. Support Calculator
# ===========================================================================

@router.post("/kpi/support/score-calculator", response_model=ApiResponse[SupportCalcResponse])
async def score_calculator(
    payload: SupportCalcRequest,
    current_user: User = OfficeAdminUp,
):
    result = support_calc_service.calculate_rates(payload)
    return ApiResponse(success=True, data=result, message="Tính toán thành công")


@router.post(
    "/kpi/records/{record_id}/support-calc",
    response_model=ApiResponse,
)
async def save_and_apply_support_calc(
    payload: SupportCalcSaveRequest,
    record_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = OfficeAdminUp,
):
    result = support_calc_service.save_and_apply(db, record_id, payload)
    return ApiResponse(success=True, data=result, message="Lưu và áp dụng thành công")


@router.get(
    "/kpi/records/{record_id}/support-calcs",
    response_model=ApiResponse[List[SupportCalcEntryResponse]],
)
async def get_support_calc_entries(
    record_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = OfficeAdminUp,
):
    entries = support_calc_service.get_calc_entries(db, record_id)
    return ApiResponse(success=True, data=entries, message="Thành công")


# ===========================================================================
# 5. Dashboard & Reports
# ===========================================================================

@router.get("/kpi/dashboard", response_model=ApiResponse[KPIDashboardSummary])
async def get_dashboard(
    period_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    data = kpi_dashboard_service.get_dashboard(db, period_id)
    return ApiResponse(success=True, data=data, message="Thành công")


@router.get("/kpi/reports/period/{period_id}/ranking", response_model=ApiResponse[List[KPIRankingItem]])
async def get_ranking(
    period_id: UUID = Path(...),
    contract_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    ranking = kpi_dashboard_service.get_ranking(db, period_id, contract_type)
    return ApiResponse(success=True, data=ranking, message="Thành công")


@router.get(
    "/kpi/reports/staff/{staff_id}/history",
    response_model=ApiResponse[List[StaffKPIHistoryItem]],
)
async def get_staff_history(
    staff_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Auth: admin or self
    is_admin = current_user.role in (UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN)
    if not is_admin and current_user.id != staff_id:
        raise HTTPException(status_code=403, detail="Không có quyền xem lịch sử KPI của người khác")

    history = kpi_dashboard_service.get_staff_history(db, staff_id)
    return ApiResponse(success=True, data=history, message="Thành công")


# ===========================================================================
# 6. Disputes
# ===========================================================================

@router.post("/kpi/dispute", response_model=ApiResponse[KpiDisputeResponse])
async def create_kpi_dispute(
    payload: KpiDisputeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dispute = kpi_dispute_service.create_dispute(db, current_user.id, payload)
    return ApiResponse(success=True, data=dispute, message="Thành công")


@router.put("/kpi/dispute/{dispute_id}/resolve", response_model=ApiResponse[KpiDisputeResponse])
async def resolve_kpi_dispute(
    dispute_id: UUID = Path(...),
    payload: KpiDisputeResolveRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    dispute = kpi_dispute_service.resolve_dispute(db, dispute_id, payload, current_user.id)
    return ApiResponse(success=True, data=dispute, message="Thành công")


# ===========================================================================
# 7. KPI Settings (deprecated — kept for backward compat)
# ===========================================================================

@router.get("/settings/kpi-tiers", response_model=ApiResponse[List[KpiTierResponse]])
async def get_kpi_tiers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tiers = kpi_settings_service.get_all_tiers(db=db)
    return ApiResponse(success=True, data=tiers, message="Thành công")


@router.put("/settings/kpi-tiers", response_model=ApiResponse[List[KpiTierResponse]])
async def update_kpi_tiers(
    payload: List[KpiTierUpdate],
    db: Session = Depends(get_db),
    current_user: User = AdminOnly,
):
    updated = kpi_settings_service.bulk_update_tiers(db=db, tiers_payload=payload)
    return ApiResponse(success=True, data=updated, message="Thành công")


# ===========================================================================
# 8. Teacher KPI Views (self / admin) — Uses new system
# ===========================================================================

@router.get("/teachers/me/kpi", response_model=ApiResponse[KPIRecordDetailResponse])
async def get_my_kpi(
    period_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detail = kpi_record_service.get_my_record(db, current_user.id, period_id)
    return ApiResponse(success=True, data=detail, message="Thành công")


def _assert_admin_or_self(current_user: User, teacher_id: UUID):
    is_admin = current_user.role in (UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN)
    if not is_admin and current_user.id != teacher_id:
        raise HTTPException(status_code=403, detail="Không có quyền xem dữ liệu của giáo viên khác")


@router.get("/teachers/{teacher_id}/kpi-history", response_model=ApiResponse[List[StaffKPIHistoryItem]])
async def get_teacher_kpi_history(
    teacher_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = TeacherOrAdmin,
):
    _assert_admin_or_self(current_user, teacher_id)
    history = kpi_dashboard_service.get_staff_history(db, teacher_id)
    return ApiResponse(success=True, data=history, message="Thành công")


# ===========================================================================
# 9. Teacher Payroll Config & Salary (kept from old system)
# ===========================================================================

@router.put(
    "/teachers/{teacher_id}/payroll-config",
    response_model=ApiResponse[TeacherPayrollConfigResponse],
)
async def update_teacher_payroll_config(
    payload: TeacherPayrollConfigUpdate,
    teacher_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    config = teacher_payroll_config_service.update_config(db, teacher_id, payload)
    return ApiResponse(success=True, data=config, message="Thành công")


@router.get("/teachers/me/salary-history", response_model=PaginationResponse[SalaryResponse])
async def get_my_salary_history(
    period: Optional[str] = Query(None, pattern=PERIOD_REGEX),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    salaries, total = salary_service.get_history(
        db, current_user.id, period, page, limit
    )
    meta = PaginationMetadata(
        page=page, limit=limit, total=total,
        total_pages=math.ceil(total / limit) if limit else 0,
    )
    return PaginationResponse(success=True, data=salaries, meta=meta, message="Thành công")


@router.get("/teachers/{teacher_id}/salary-history", response_model=PaginationResponse[SalaryResponse])
async def get_teacher_salary_history(
    teacher_id: UUID = Path(...),
    period: Optional[str] = Query(None, pattern=PERIOD_REGEX),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = TeacherOrAdmin,
):
    _assert_admin_or_self(current_user, teacher_id)
    salaries, total = salary_service.get_history(db, teacher_id, period, page, limit)
    meta = PaginationMetadata(
        page=page, limit=limit, total=total,
        total_pages=math.ceil(total / limit) if limit else 0,
    )
    return PaginationResponse(success=True, data=salaries, meta=meta, message="Thành công")


# ===========================================================================
# 10. Payroll Runs & Salaries (kept from old system)
# ===========================================================================

@router.post("/payroll-runs", response_model=ApiResponse[PayrollRunResponse])
async def create_payroll_run(
    payload: PayrollRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    run = payroll_run_service.create_run(db, payload, background_tasks)
    return ApiResponse(success=True, data=run, message="Thành công")


@router.get("/salaries", response_model=PaginationResponse[SalaryResponse])
async def get_salaries(
    period: Optional[str] = Query(None, pattern=PERIOD_REGEX),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    salaries, total = salary_service.get_all(db, period, page, limit)
    meta = PaginationMetadata(
        page=page, limit=limit, total=total,
        total_pages=math.ceil(total / limit) if limit else 0,
    )
    return PaginationResponse(success=True, data=salaries, meta=meta, message="Thành công")


@router.get("/salaries/{salary_id}", response_model=ApiResponse[SalaryResponse])
async def get_salary_detail(
    salary_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    salary = salary_service.get_salary(db, salary_id, current_user)
    return ApiResponse(success=True, data=salary, message="Thành công")


@router.post("/salaries/{salary_id}/approve", response_model=ApiResponse[SalaryResponse])
async def approve_salary(
    salary_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    salary = salary_service.approve(db, salary_id, current_user.id)
    return ApiResponse(success=True, data=salary, message="Thành công")


@router.patch(
    "/salaries/{salary_id}/adjustments",
    response_model=ApiResponse[SalaryAdjustmentResponse],
)
async def add_salary_adjustment(
    payload: SalaryAdjustmentCreate,
    salary_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    adj = salary_service.add_adjustment(db, salary_id, payload, current_user.id)
    return ApiResponse(success=True, data=adj, message="Thành công")


# ===========================================================================
# 11. Bulk Period Calculation
# ===========================================================================

@router.post("/kpi/periods/{period_id}/calculate-all", response_model=ApiResponse)
async def bulk_calculate_period(
    period_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = CenterAdminUp,
):
    result = kpi_calculation_service.bulk_calculate_period(db, period_id)
    return ApiResponse(success=True, data=result, message="Tính toán hàng loạt thành công")