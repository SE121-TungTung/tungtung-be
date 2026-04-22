from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import List, Optional, Any, Dict
from datetime import datetime, date
from uuid import UUID
from decimal import Decimal

from app.models.kpi import (
    ActiveStatus, ContractType, JobStatus,
    DisputeStatus, SalaryStatus, AdjustmentType,
    MetricUnit, ApprovalStatus, DataSource, PeriodType,
    BonusType, ApprovalAction,
)

# ---------------------------------------------------------------------------
# Shared constants & validators
# ---------------------------------------------------------------------------
PERIOD_REGEX = r"^\d{4}-(0[1-9]|1[0-2])$"


# ============================================================================
# KPI Template
# ============================================================================

class KPITemplateMetricBase(BaseModel):
    metric_code    : str = Field(..., max_length=10)
    metric_name    : str = Field(..., max_length=255)
    is_group_header: bool = Field(default=False)
    unit           : Optional[MetricUnit] = None
    target_min     : Optional[float] = None
    target_max     : Optional[float] = None
    weight         : Optional[float] = None
    group_weight   : Optional[float] = None
    sort_order     : int = Field(default=0)
    description    : Optional[str] = None


class KPITemplateMetricCreate(KPITemplateMetricBase):
    pass


class KPITemplateMetricUpdate(KPITemplateMetricBase):
    id: Optional[UUID] = None


class KPITemplateMetricResponse(KPITemplateMetricBase):
    id         : UUID
    template_id: UUID
    model_config = ConfigDict(from_attributes=True)


class KPITemplateCreate(BaseModel):
    name            : str = Field(..., max_length=200)
    contract_type   : ContractType
    max_bonus_amount: float = Field(..., ge=0)
    bonus_type      : BonusType = BonusType.FIXED_PER_PERIOD
    effective_from  : Optional[date] = None
    description     : Optional[str] = None
    metrics         : List[KPITemplateMetricCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_weights(self) -> "KPITemplateCreate":
        """Validate that non-group-header metric weights sum to ~1.0."""
        metric_weights = [
            m.weight for m in self.metrics
            if not m.is_group_header and m.weight is not None
        ]
        if metric_weights:
            total = sum(metric_weights)
            if not (0.99 <= total <= 1.01):
                raise ValueError(
                    f"Tổng trọng số các tiêu chí phải bằng 1.0 (hiện tại: {total:.4f})"
                )
        return self


class KPITemplateUpdate(BaseModel):
    name            : Optional[str] = Field(None, max_length=200)
    max_bonus_amount: Optional[float] = Field(None, ge=0)
    bonus_type      : Optional[BonusType] = None
    effective_from  : Optional[date] = None
    description     : Optional[str] = None
    is_active       : Optional[bool] = None
    metrics         : Optional[List[KPITemplateMetricUpdate]] = None


class KPITemplateResponse(BaseModel):
    id              : UUID
    name            : str
    contract_type   : ContractType
    max_bonus_amount: float
    bonus_type      : BonusType
    version         : int
    effective_from  : Optional[date] = None
    is_active       : bool
    description     : Optional[str] = None
    created_at      : Optional[datetime] = None
    metrics         : List[KPITemplateMetricResponse] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class KPITemplateListResponse(BaseModel):
    id              : UUID
    name            : str
    contract_type   : ContractType
    max_bonus_amount: float
    bonus_type      : BonusType
    version         : int
    is_active       : bool
    created_at      : Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# KPI Period
# ============================================================================

class KPIPeriodCreate(BaseModel):
    name       : str = Field(..., max_length=100)
    period_type: PeriodType = PeriodType.SEMESTER
    start_date : date
    end_date   : date

    @model_validator(mode="after")
    def validate_dates(self) -> "KPIPeriodCreate":
        if self.start_date >= self.end_date:
            raise ValueError("start_date phải trước end_date")
        return self


class KPIPeriodResponse(BaseModel):
    id         : UUID
    name       : str
    period_type: PeriodType
    start_date : date
    end_date   : date
    is_active  : bool
    created_at : Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class KPIPeriodDetailResponse(KPIPeriodResponse):
    total_records     : int = 0
    submitted_count   : int = 0
    approved_count    : int = 0
    draft_count       : int = 0
    rejected_count    : int = 0


# ============================================================================
# KPI Record
# ============================================================================

class MetricActualValueInput(BaseModel):
    metric_code : str
    actual_value: float


class MetricResultResponse(BaseModel):
    id             : UUID
    metric_code    : str
    metric_name    : str
    is_group_header: bool = False
    unit           : Optional[MetricUnit] = None
    target_min     : Optional[float] = None
    target_max     : Optional[float] = None
    weight         : Optional[float] = None
    group_weight   : Optional[float] = None
    actual_value   : Optional[float] = None
    converted_score: Optional[float] = None
    data_source    : Optional[DataSource] = None
    note           : Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class KPIRecordListItem(BaseModel):
    id              : UUID
    staff_id        : UUID
    staff_name      : Optional[str] = None
    staff_contract  : Optional[ContractType] = None
    period_id       : UUID
    period_name     : Optional[str] = None
    total_score     : Optional[float] = None
    bonus_amount    : Optional[float] = None
    teaching_hours  : Optional[float] = None
    approval_status : ApprovalStatus
    submitted_at    : Optional[datetime] = None
    approved_at     : Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class KPIRecordDetailResponse(BaseModel):
    id              : UUID
    staff_id        : UUID
    staff_name      : Optional[str] = None
    staff_contract  : Optional[ContractType] = None
    period          : KPIPeriodResponse
    template        : KPITemplateListResponse
    total_score     : Optional[float] = None
    bonus_amount    : Optional[float] = None
    teaching_hours  : Optional[float] = None
    approval_status : ApprovalStatus
    submitted_at    : Optional[datetime] = None
    approved_by     : Optional[UUID] = None
    approved_at     : Optional[datetime] = None
    rejection_note  : Optional[str] = None
    metrics         : List[MetricResultResponse] = Field(default_factory=list)
    model_config = ConfigDict(from_attributes=True)


class UpdateMetricsRequest(BaseModel):
    metrics: List[MetricActualValueInput]


class UpdateTeachingHoursRequest(BaseModel):
    teaching_hours: float = Field(..., ge=0)


# ============================================================================
# Support Calculator
# ============================================================================

class SupportCalcRequest(BaseModel):
    class_size      : int = Field(..., gt=0)
    max_score       : float = Field(..., gt=0)
    avg_threshold   : float = Field(..., ge=0)
    above_avg_count : int = Field(..., ge=0, description="Số HS đạt TB (không tính HS đạt điểm cao)")
    high_threshold  : float = Field(..., ge=0)
    above_high_count: int = Field(..., ge=0)
    class_name      : Optional[str] = None

    @model_validator(mode="after")
    def validate_counts(self) -> "SupportCalcRequest":
        total_above = self.above_avg_count + self.above_high_count
        if total_above > self.class_size:
            raise ValueError(
                f"Tổng HS đạt TB ({self.above_avg_count}) + đạt cao ({self.above_high_count}) "
                f"không thể vượt sĩ số lớp ({self.class_size})"
            )
        if self.avg_threshold > self.max_score:
            raise ValueError("Ngưỡng TB không thể lớn hơn điểm tối đa")
        if self.high_threshold > self.max_score:
            raise ValueError("Ngưỡng cao không thể lớn hơn điểm tối đa")
        if self.high_threshold < self.avg_threshold:
            raise ValueError("Ngưỡng cao phải >= ngưỡng trung bình")
        return self


class SupportCalcResponse(BaseModel):
    rate_above_avg : float
    rate_above_high: float
    breakdown      : Dict[str, Any]

    model_config = ConfigDict(from_attributes=True)


class SupportCalcSaveRequest(SupportCalcRequest):
    """Save and apply the calculator result to a KPI record's A1/A2."""
    pass


class SupportCalcEntryResponse(BaseModel):
    id              : UUID
    kpi_record_id   : UUID
    class_name      : Optional[str] = None
    class_size      : int
    max_score       : float
    avg_threshold   : float
    above_avg_count : int
    high_threshold  : float
    above_high_count: int
    rate_above_avg  : float
    rate_above_high : float
    created_at      : Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Approval Log
# ============================================================================

class KPIApprovalLogResponse(BaseModel):
    id            : UUID
    kpi_record_id : UUID
    action        : ApprovalAction
    actor_id      : UUID
    comment       : Optional[str] = None
    created_at    : Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class RejectRequest(BaseModel):
    comment: str = Field(..., min_length=5, description="Lý do từ chối (bắt buộc)")


# ============================================================================
# Dashboard & Reports
# ============================================================================

class KPIDashboardSummary(BaseModel):
    period_id         : UUID
    period_name       : str
    total_staff       : int = 0
    total_teachers    : int = 0
    total_ta          : int = 0
    approved_count    : int = 0
    submitted_count   : int = 0
    draft_count       : int = 0
    rejected_count    : int = 0
    avg_score         : Optional[float] = None
    total_bonus_amount: Optional[float] = None
    top_performers    : List[Dict[str, Any]] = Field(default_factory=list)
    alerts            : List[Dict[str, Any]] = Field(default_factory=list)


class KPIRankingItem(BaseModel):
    rank           : int
    staff_id       : UUID
    staff_name     : str
    contract_type  : Optional[ContractType] = None
    total_score    : float
    bonus_amount   : float
    approval_status: ApprovalStatus


class StaffKPIHistoryItem(BaseModel):
    period_id      : UUID
    period_name    : str
    total_score    : Optional[float] = None
    bonus_amount   : Optional[float] = None
    approval_status: ApprovalStatus


# ============================================================================
# Deprecated schemas (kept for payroll backward compat)
# ============================================================================

class KpiTierBase(BaseModel):
    tier_name         : str   = Field(..., max_length=20)
    min_score         : float = Field(..., ge=0)
    max_score         : float = Field(..., le=100)
    reward_percentage : float = Field(..., ge=0)
    reward_per_lesson : float = Field(default=0, ge=0)
    status            : ActiveStatus = Field(default=ActiveStatus.ACTIVE)

    @model_validator(mode="after")
    def validate_score_range(self) -> "KpiTierBase":
        if self.min_score >= self.max_score:
            raise ValueError(
                f"min_score ({self.min_score}) phải nhỏ hơn max_score ({self.max_score})"
            )
        return self

class KpiTierUpdate(KpiTierBase):
    id: Optional[int] = Field(default=None)

class KpiTierResponse(KpiTierBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# Teacher Payroll Config
class TeacherPayrollConfigUpdate(BaseModel):
    contract_type   : ContractType
    base_salary     : float = Field(default=0, ge=0)
    lesson_rate     : float = Field(default=0, ge=0)
    max_kpi_bonus   : float = Field(default=0, ge=0)
    fixed_allowance : float = Field(default=0, ge=0)

class TeacherPayrollConfigResponse(TeacherPayrollConfigUpdate):
    teacher_id : UUID
    updated_at : datetime
    model_config = ConfigDict(from_attributes=True)


# KPI Calculation Job (deprecated)
class KpiCalculationJobCreate(BaseModel):
    period: str = Field(..., pattern=PERIOD_REGEX)
    force: bool = Field(default=False, description="Bắt buộc tính lại dù đã có dữ liệu")

class KpiCalculationJobResponse(BaseModel):
    job_id          : UUID
    period          : str
    status          : JobStatus
    total_teachers  : int
    processed_count : int
    error_log       : Optional[str] = None
    started_at      : datetime
    finished_at     : Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# Monthly KPI (deprecated)
class KpiCriteriaScoreItem(BaseModel):
    code      : str
    score     : float = Field(..., ge=0)
    max_score : float = Field(..., gt=0)

class KpiDetails(BaseModel):
    criteria_scores: List[KpiCriteriaScoreItem]

class TeacherMonthlyKpiResponse(BaseModel):
    id               : UUID
    teacher_id       : UUID
    period           : str
    total_score      : float
    kpi_tier_id      : Optional[int] = None
    kpi_details      : KpiDetails
    calculated_bonus : float
    created_at       : datetime
    model_config = ConfigDict(from_attributes=True)

class KpiRawMetricSync(BaseModel):
    teacher_id    : UUID
    period        : str = Field(...)
    source_module : str = Field(..., max_length=50)
    metric_data   : Dict[str, Any]


# KPI Dispute (migrated to KPIRecord)
class KpiDisputeCreate(BaseModel):
    kpi_record_id: UUID
    reason       : str = Field(..., min_length=10)

class KpiDisputeResponse(BaseModel):
    id              : UUID
    kpi_record_id   : Optional[UUID] = None
    kpi_id          : Optional[UUID] = None
    teacher_id      : UUID
    reason          : str
    status          : DisputeStatus
    resolved_by     : Optional[UUID] = None
    resolution_note : Optional[str]  = None
    created_at      : datetime
    resolved_at     : Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class KpiDisputeResolveRequest(BaseModel):
    status          : DisputeStatus = Field(..., description="Kết quả xử lý: RESOLVED hoặc REJECTED")
    resolution_note : str = Field(..., min_length=5, description="Ghi chú kết quả xử lý (bắt buộc)")

    @field_validator("status")
    @classmethod
    def must_be_terminal_status(cls, v: DisputeStatus) -> DisputeStatus:
        if v == DisputeStatus.PENDING:
            raise ValueError("Không thể resolve dispute với status PENDING")
        return v


# Salary
class SalaryResponse(BaseModel):
    id                : UUID
    teacher_id        : UUID
    period            : str
    contract_type     : ContractType
    lesson_count      : int
    base_salary_calc  : float
    kpi_bonus_calc    : float
    fixed_allowance   : float
    total_adjustments : float
    net_salary        : float
    status            : SalaryStatus
    approved_by       : Optional[UUID] = None
    approved_at       : Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class SalaryAdjustmentCreate(BaseModel):
    adjustment_type : AdjustmentType
    amount          : float = Field(..., gt=0, description=(
            "Luôn là số dương. Service tự đổi dấu khi adjustment_type=DEDUCTION "
            "khi tính net_salary."))
    reason          : str   = Field(..., max_length=255)

class SalaryAdjustmentResponse(SalaryAdjustmentCreate):
    id         : UUID
    salary_id  : UUID
    created_at : datetime
    model_config = ConfigDict(from_attributes=True)


# Payroll Run
class PayrollRunResponse(BaseModel):
    id              : UUID
    period          : str
    status          : JobStatus
    total_processed : int
    error_log       : Optional[str]      = None
    finished_at     : Optional[datetime] = None
    created_at      : datetime
    model_config = ConfigDict(from_attributes=True)

class PayrollRunCreate(BaseModel):
    period: str = Field(..., pattern=PERIOD_REGEX)


# KPI Summary (deprecated — use Dashboard instead)
from app.schemas.base_schema import PaginationMetadata

class KpiSummaryItem(BaseModel):
    teacher_id      : UUID
    teacher_name    : str
    total_kpi_score : Optional[float] = None
    tier            : Optional[str] = None
    metrics         : Dict[str, float] = Field(default_factory=dict)
    status          : str

class KpiSummaryPeriodMeta(PaginationMetadata):
    period_status   : str