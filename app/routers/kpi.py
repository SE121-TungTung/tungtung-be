from fastapi import APIRouter, Depends, Query, Path, Body, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Annotated
from uuid import UUID
import math

from app.core.database import get_db
from app.dependencies import get_current_user, require_role
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.models.user import User

from app.schemas.kpi import (
    KpiTierResponse, KpiTierUpdate,
    KpiCalculationJobCreate, KpiCalculationJobResponse,
    TeacherMonthlyKpiResponse, TeacherPayrollConfigUpdate, TeacherPayrollConfigResponse,
    KpiRawMetricSync,
    KpiDisputeCreate, KpiDisputeResponse, KpiDisputeResolveRequest,
    SalaryResponse, SalaryAdjustmentCreate, SalaryAdjustmentResponse,
    PayrollRunCreate, PayrollRunResponse,
    PERIOD_REGEX
)

from app.services.kpi.settings_service import KpiSettingsService
from app.services.kpi.calculation_service import KpiCalculationService
from app.services.kpi.metric_service import KpiMetricService
from app.services.kpi.dispute_service import KpiDisputeService
from app.services.kpi.payroll_service import SalaryService, TeacherPayrollConfigService, PayrollRunService

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
    tiers = KpiSettingsService(db).get_all_tiers()
    return ApiResponse(success=True, data=tiers, message="Thành công")

@router.put("/settings/kpi-tiers", response_model=ApiResponse[List[KpiTierResponse]])
async def update_kpi_tiers(
    payload: List[KpiTierUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin"))
):
    updated_tiers = KpiSettingsService(db).bulk_update_tiers(payload)
    return ApiResponse(success=True, data=updated_tiers, message="Thành công")

# ---------------------------------------------------------------------------
# KPI Calculation Jobs
# ---------------------------------------------------------------------------
@router.post("/kpi/calculation-jobs", response_model=ApiResponse[KpiCalculationJobResponse])
async def create_kpi_calculation_job(
    payload: KpiCalculationJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("center_admin"))
):
    job_info = KpiCalculationService(db).trigger_calculation_job(payload, background_tasks)
    return ApiResponse(success=True, data=job_info, message="Thành công")

@router.get("/kpi/calculation-jobs/{job_id}", response_model=ApiResponse[KpiCalculationJobResponse])
async def get_kpi_calculation_job(
    job_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("center_admin"))
):
    job = KpiCalculationService(db).get_job(job_id)
    return ApiResponse(success=True, data=job, message="Thành công")

# ---------------------------------------------------------------------------
# KPI Metrics Sync
# ---------------------------------------------------------------------------
@router.post("/kpi/metrics/sync", response_model=ApiResponse[str])
async def sync_raw_metrics(
    payload: KpiRawMetricSync,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("system_admin"))
):
    msg = KpiMetricService(db).sync_metrics(payload)
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
    dispute = KpiDisputeService(db).create_dispute(current_user.id, payload)
    return ApiResponse(success=True, data=dispute, message="Thành công")

@router.put("/kpi/dispute/{id}/resolve", response_model=ApiResponse[KpiDisputeResponse])
async def resolve_kpi_dispute(
    id: UUID = Path(...),
    payload: KpiDisputeResolveRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("center_admin")),
):
    dispute = KpiDisputeService(db).resolve_dispute(id, payload, current_user.id)
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
    salaries, total = SalaryService(db).get_history(current_user.id, period, page, limit)
    meta = PaginationMetadata(page=page, limit=limit, total=total, total_pages=math.ceil(total / limit) if limit else 0)
    return PaginationResponse(success=True, data=salaries, meta=meta, message="Thành công")

@router.get("/teachers/me/kpi", response_model=ApiResponse[TeacherMonthlyKpiResponse])
async def get_my_kpi(
    period: PeriodQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kpi = KpiCalculationService(db).get_teacher_kpi(current_user.id, period)
    return ApiResponse(success=True, data=kpi, message="Thành công")

# ---------------------------------------------------------------------------
# Teacher KPI & Payroll Config (Dynamic Paths)
# ---------------------------------------------------------------------------
@router.get("/teachers/{teacher_id}/kpi", response_model=ApiResponse[TeacherMonthlyKpiResponse])
async def get_teacher_monthly_kpi(
    teacher_id: UUID = Path(...),
    period: PeriodQuery = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("center_admin"))
):
    kpi = KpiCalculationService(db).get_teacher_kpi(teacher_id, period)
    return ApiResponse(success=True, data=kpi, message="Thành công")

@router.put("/teachers/{teacher_id}/payroll-config", response_model=ApiResponse[TeacherPayrollConfigResponse])
async def update_teacher_payroll_config(
    payload: TeacherPayrollConfigUpdate,
    teacher_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("center_admin"))
):
    config = TeacherPayrollConfigService(db).update_config(teacher_id, payload)
    return ApiResponse(success=True, data=config, message="Thành công")

# ---------------------------------------------------------------------------
# Payroll Runs
# ---------------------------------------------------------------------------
@router.post("/payroll-runs", response_model=ApiResponse[PayrollRunResponse])
async def create_payroll_run(
    payload: PayrollRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("center_admin"))
):
    run = PayrollRunService(db).create_run(payload, background_tasks)
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
    current_user: User = Depends(require_role("center_admin")),
):
    salaries, total = SalaryService(db).get_all(period, page, limit)
    meta = PaginationMetadata(page=page, limit=limit, total=total, total_pages=math.ceil(total / limit) if limit else 0)
    return PaginationResponse(success=True, data=salaries, meta=meta, message="Thành công")

@router.get("/salaries/{id}", response_model=ApiResponse[SalaryResponse])
async def get_salary_detail(
    id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    salary = SalaryService(db).get_salary(id, current_user)
    return ApiResponse(success=True, data=salary, message="Thành công")

@router.post("/salaries/{id}/approve", response_model=ApiResponse[SalaryResponse])
async def approve_salary(
    id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("center_admin")),
):
    salary = SalaryService(db).approve(id, current_user.id)
    return ApiResponse(success=True, data=salary, message="Thành công")

@router.patch("/salaries/{salary_id}/adjustments", response_model=ApiResponse[SalaryAdjustmentResponse])
async def add_salary_adjustment(
    payload: SalaryAdjustmentCreate,
    salary_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("center_admin")),
):
    adjustment = SalaryService(db).add_adjustment(salary_id, payload, current_user.id)
    return ApiResponse(success=True, data=adjustment, message="Thành công")