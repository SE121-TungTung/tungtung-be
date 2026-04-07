from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import List, Optional, Any, Dict
from datetime import datetime
from uuid import UUID
import re

from app.models.kpi import (
    ActiveStatus, ContractType, JobStatus,
    DisputeStatus, SalaryStatus, AdjustmentType,
)

# ---------------------------------------------------------------------------
# Shared constants & validators
# ---------------------------------------------------------------------------
PERIOD_REGEX = r"^\d{4}-(0[1-9]|1[0-2])$"

# ---------------------------------------------------------------------------
# KPI Tier
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Teacher Payroll Config
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# KPI Calculation Job
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Monthly KPI
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# KPI Dispute
# ---------------------------------------------------------------------------
class KpiDisputeCreate(BaseModel):
    kpi_id : UUID
    reason : str = Field(..., min_length=10)

class KpiDisputeResponse(BaseModel):
    id              : UUID
    kpi_id          : UUID
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

# ---------------------------------------------------------------------------
# Salary
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Payroll Run
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# KPI Summary
# ---------------------------------------------------------------------------
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

class KpiSummaryResponse(BaseModel):
    success : bool = True
    data    : List[KpiSummaryItem]
    message : Optional[str] = None
    meta    : Optional[KpiSummaryPeriodMeta] = None

    model_config = ConfigDict(from_attributes=True)