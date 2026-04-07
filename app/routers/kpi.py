from fastapi import APIRouter, Depends, Query, Path, Body, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Annotated
from uuid import UUID
import math

from app.core.database import get_db
from app.dependencies import get_current_user, require_role, get_current_admin_user
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.models.user import User, UserRole

from app.schemas.kpi import (
    KpiTierResponse, KpiTierUpdate,
    KpiCalculationJobCreate, KpiCalculationJobResponse,
    TeacherMonthlyKpiResponse, TeacherPayrollConfigUpdate, TeacherPayrollConfigResponse,
    KpiRawMetricSync,
    KpiDisputeCreate, KpiDisputeResponse, KpiDisputeResolveRequest,
    SalaryResponse, SalaryAdjustmentCreate, SalaryAdjustmentResponse,
    PayrollRunCreate, PayrollRunResponse,
    PERIOD_REGEX, KpiSummaryResponse
)

from app.services.kpi.settings_service import kpi_settings_service
from app.services.kpi.calculation_service import kpi_calculation_service
from app.services.kpi.metric_service import kpi_metric_service
from app.services.kpi.dispute_service import kpi_dispute_service
from app.services.kpi.payroll_service import salary_service, teacher_payroll_config_service, payroll_run_service

router = APIRouter(prefix="", tags=["KPI & Payroll"])

PeriodQuery = Annotated[str, Query(pattern=PERIOD_REGEX)]
OptionalPeriodQuery = Annotated[Optional[str], Query(pattern=PERIOD_REGEX)]

# ---------------------------------------------------------------------------
# KPI Settings
# ---------------------------------------------------------------------------
@router.get("/settings/kpi-tiers", response_model=ApiResponse[List[KpiTierResponse]])
async def get_kpi_tiers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tiers = kpi_settings_service.get_all_tiers(db=db)
    return ApiResponse(success=True, data=tiers, message="Thành công")

@router.put("/settings/kpi-tiers", response_model=ApiResponse[List[KpiTierResponse]])
async def update_kpi_tiers(
    payload: List[KpiTierUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SYSTEM_ADMIN))
):
    updated_tiers = kpi_settings_service.bulk_update_tiers(db=db, tiers_payload=payload)
    return ApiResponse(success=True, data=updated_tiers, message="Thành công")

# ---------------------------------------------------------------------------
# KPI Calculation Jobs
# ---------------------------------------------------------------------------
@router.post("/kpi/calculation-jobs", response_model=ApiResponse[KpiCalculationJobResponse])
async def create_kpi_calculation_job(
    payload: KpiCalculationJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CENTER_ADMIN))
):
    job_info = kpi_calculation_service.trigger_calculation_job(db=db, payload=payload, bg_tasks=background_tasks)
    return ApiResponse(success=True, data=job_info, message="Thành công")

@router.get("/kpi/calculation-jobs/{job_id}", response_model=ApiResponse[KpiCalculationJobResponse])
async def get_kpi_calculation_job(
    job_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CENTER_ADMIN))
):
    job = kpi_calculation_service.get_job(db=db, job_id=job_id)
    return ApiResponse(success=True, data=job, message="Thành công")

@router.get("/kpi/summary", response_model=KpiSummaryResponse)
async def get_kpi_summary(
    period: PeriodQuery,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    summary, meta = kpi_calculation_service.get_summary(db=db, period=period, page=page, limit=limit)
    return KpiSummaryResponse(success=True, data=summary, meta=meta, message="Thành công")

# ---------------------------------------------------------------------------
# KPI Metrics Sync
# ---------------------------------------------------------------------------
@router.post("/kpi/metrics/sync", response_model=ApiResponse[str])
async def sync_raw_metrics(
    payload: KpiRawMetricSync,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.SYSTEM_ADMIN))
):
    msg = kpi_metric_service.sync_metrics(db=db, payload=payload)
    return ApiResponse(success=True, data=msg, message="Thành công")

# ---------------------------------------------------------------------------
# KPI Dispute
# ---------------------------------------------------------------------------
@router.post("/kpi/dispute", response_model=ApiResponse[KpiDisputeResponse])
async def create_kpi_dispute(
    payload: KpiDisputeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dispute = kpi_dispute_service.create_dispute(db=db, teacher_id=current_user.id, payload=payload)
    return ApiResponse(success=True, data=dispute, message="Thành công")

@router.put("/kpi/dispute/{id}/resolve", response_model=ApiResponse[KpiDisputeResponse])
async def resolve_kpi_dispute(
    id: UUID = Path(...),
    payload: KpiDisputeResolveRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CENTER_ADMIN)),
):
    dispute = kpi_dispute_service.resolve_dispute(db=db, dispute_id=id, payload=payload, admin_id=current_user.id)
    return ApiResponse(success=True, data=dispute, message="Thành công")

# ---------------------------------------------------------------------------
# Teacher KPI & Payroll Config (Static Paths First)
# ---------------------------------------------------------------------------
@router.get("/teachers/me/salary-history", response_model=PaginationResponse[SalaryResponse])
async def get_my_salary_history(
    period: OptionalPeriodQuery = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    salaries, total = salary_service.get_history(db=db, teacher_id=current_user.id, period=period, page=page, limit=limit)
    meta = PaginationMetadata(page=page, limit=limit, total=total, total_pages=math.ceil(total / limit) if limit else 0)
    return PaginationResponse(success=True, data=salaries, meta=meta, message="Thành công")

@router.get("/teachers/me/kpi", response_model=ApiResponse[TeacherMonthlyKpiResponse])
async def get_my_kpi(
    period: PeriodQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kpi = kpi_calculation_service.get_teacher_kpi(db=db, teacher_id=current_user.id, period=period)
    return ApiResponse(success=True, data=kpi, message="Thành công")

# ---------------------------------------------------------------------------
# Teacher KPI & Payroll Config (Dynamic Paths)
# ---------------------------------------------------------------------------
@router.get("/teachers/{teacher_id}/kpi", response_model=ApiResponse[TeacherMonthlyKpiResponse])
async def get_teacher_monthly_kpi(
    teacher_id: UUID = Path(...),
    period: PeriodQuery = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CENTER_ADMIN))
):
    kpi = kpi_calculation_service.get_teacher_kpi(db=db, teacher_id=teacher_id, period=period)
    return ApiResponse(success=True, data=kpi, message="Thành công")

@router.put("/teachers/{teacher_id}/payroll-config", response_model=ApiResponse[TeacherPayrollConfigResponse])
async def update_teacher_payroll_config(
    payload: TeacherPayrollConfigUpdate,
    teacher_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CENTER_ADMIN))
):
    config = teacher_payroll_config_service.update_config(db=db, teacher_id=teacher_id, payload=payload)
    return ApiResponse(success=True, data=config, message="Thành công")

# ---------------------------------------------------------------------------
# Payroll Runs
# ---------------------------------------------------------------------------
@router.post("/payroll-runs", response_model=ApiResponse[PayrollRunResponse])
async def create_payroll_run(
    payload: PayrollRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CENTER_ADMIN))
):
    run = payroll_run_service.create_run(db=db, payload=payload, bg_tasks=background_tasks)
    return ApiResponse(success=True, data=run, message="Thành công")

# ---------------------------------------------------------------------------
# Salaries
# ---------------------------------------------------------------------------
@router.get("/salaries", response_model=PaginationResponse[SalaryResponse])
async def get_salaries(
    period: OptionalPeriodQuery = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CENTER_ADMIN)),
):
    salaries, total = salary_service.get_all(db=db, period=period, page=page, limit=limit)
    meta = PaginationMetadata(page=page, limit=limit, total=total, total_pages=math.ceil(total / limit) if limit else 0)
    return PaginationResponse(success=True, data=salaries, meta=meta, message="Thành công")

@router.get("/salaries/{id}", response_model=ApiResponse[SalaryResponse])
async def get_salary_detail(
    id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    salary = salary_service.get_salary(db=db, salary_id=id, current_user=current_user)
    return ApiResponse(success=True, data=salary, message="Thành công")

@router.post("/salaries/{id}/approve", response_model=ApiResponse[SalaryResponse])
async def approve_salary(
    id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CENTER_ADMIN)),
):
    salary = salary_service.approve(db=db, salary_id=id, admin_id=current_user.id)
    return ApiResponse(success=True, data=salary, message="Thành công")

@router.patch("/salaries/{salary_id}/adjustments", response_model=ApiResponse[SalaryAdjustmentResponse])
async def add_salary_adjustment(
    payload: SalaryAdjustmentCreate,
    salary_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CENTER_ADMIN)),
):
    adjustment = salary_service.add_adjustment(db=db, salary_id=salary_id, payload=payload, admin_id=current_user.id)
    return ApiResponse(success=True, data=adjustment, message="Thành công")