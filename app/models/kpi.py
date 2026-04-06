import enum
import uuid
from sqlalchemy import (
    Column, Integer, String, Numeric, ForeignKey, JSON,
    DateTime, CheckConstraint, UniqueConstraint, Enum, Text
)
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ContractType(str, enum.Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    NATIVE    = "NATIVE"


class JobStatus(str, enum.Enum):
    PENDING    = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"


class ActiveStatus(str, enum.Enum):
    ACTIVE   = "ACTIVE"
    INACTIVE = "INACTIVE"


class DisputeStatus(str, enum.Enum):
    PENDING  = "PENDING"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"


class SalaryStatus(str, enum.Enum):
    DRAFT    = "DRAFT"
    APPROVED = "APPROVED"
    PAID     = "PAID"


class AdjustmentType(str, enum.Enum):
    ALLOWANCE = "ALLOWANCE"
    DEDUCTION = "DEDUCTION"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    setting_key   = Column(String(50), unique=True, nullable=False)
    setting_value = Column(String(255), nullable=False)
    description   = Column(String(255), nullable=True)


class KpiTier(Base):
    __tablename__ = "kpi_tiers"
    __table_args__ = (
        CheckConstraint("min_score >= 0",           name="check_min_score_positive"),
        CheckConstraint("max_score <= 100",          name="check_max_score_limit"),
        CheckConstraint("min_score < max_score",     name="check_min_less_than_max"),
        CheckConstraint("reward_percentage >= 0",    name="check_reward_positive"),
        CheckConstraint("reward_per_lesson >= 0",    name="check_reward_per_lesson"),
    )

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    tier_name          = Column(String(20), nullable=False, unique=True)
    min_score          = Column(Numeric(5, 2), nullable=False)
    max_score          = Column(Numeric(5, 2), nullable=False)
    reward_percentage  = Column(Numeric(5, 2), nullable=False)
    # FIX #5: reward_per_lesson dùng cho Part-time / Native contract
    reward_per_lesson  = Column(Numeric(15, 2), default=0)
    status             = Column(
        Enum(ActiveStatus, native_enum=True, name="kpi_tier_status_enum"),
        default=ActiveStatus.ACTIVE,
    )


class KpiCriteria(Base):
    __tablename__ = "kpi_criterias"
    __table_args__ = (
        CheckConstraint("weight_percent > 0", name="check_weight_positive"),
    )

    id             = Column(Integer, primary_key=True, autoincrement=True)
    criteria_code  = Column(String(50), unique=True, nullable=False)
    criteria_name  = Column(String(100), nullable=False)
    weight_percent = Column(Numeric(5, 2), nullable=False)
    status         = Column(
        Enum(ActiveStatus, native_enum=True, name="kpi_criteria_status_enum"),
        default=ActiveStatus.ACTIVE,
    )


class TeacherPayrollConfig(Base):
    __tablename__ = "teacher_payroll_configs"
    __table_args__ = (
        CheckConstraint("base_salary >= 0",    name="check_base_salary"),
        CheckConstraint("lesson_rate >= 0",    name="check_lesson_rate"),
        CheckConstraint("max_kpi_bonus >= 0",  name="check_max_kpi_bonus"),
    )

    teacher_id    = Column(UUID(as_uuid=True), primary_key=True)
    contract_type = Column(
        Enum(ContractType, native_enum=True, name="payroll_config_contract_type_enum"),
        nullable=False,
    )
    base_salary     = Column(Numeric(15, 2), default=0)
    lesson_rate     = Column(Numeric(15, 2), default=0)
    max_kpi_bonus   = Column(Numeric(15, 2), default=0)
    fixed_allowance = Column(Numeric(15, 2), default=0)
    updated_at      = Column(DateTime, default=func.now(), onupdate=func.now())


class TeacherMonthlyKpi(Base):
    __tablename__ = "teacher_monthly_kpis"
    __table_args__ = (
        UniqueConstraint("teacher_id", "period", name="uix_teacher_period"),
        CheckConstraint(
            "total_score >= 0 AND total_score <= 100",
            name="check_total_score",
        ),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id       = Column(UUID(as_uuid=True), nullable=False)
    period           = Column(String(7), nullable=False)
    total_score      = Column(Numeric(5, 2), nullable=False)
    kpi_tier_id      = Column(Integer, ForeignKey("kpi_tiers.id"), nullable=True)
    kpi_details      = Column(JSON, nullable=False)
    calculated_bonus = Column(Numeric(15, 2), default=0)
    created_at       = Column(DateTime, default=func.now())
    finalized_at     = Column(DateTime, nullable=True)


class KpiCalculationJob(Base):
    __tablename__ = "kpi_calculation_jobs"

    job_id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period          = Column(String(7), nullable=False)
    status          = Column(
        Enum(JobStatus, native_enum=True, name="job_status_enum"),
        default=JobStatus.PENDING,
    )
    total_teachers  = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    error_log       = Column(Text, nullable=True)
    started_at      = Column(DateTime, default=func.now())
    finished_at     = Column(DateTime, nullable=True)


# FIX #10: Bổ sung error_log và finished_at vào PayrollRun
class PayrollRun(Base):
    __tablename__ = "payroll_runs"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period          = Column(String(7), unique=True, nullable=False)
    status          = Column(
        Enum(JobStatus, native_enum=True, name="payroll_run_status_enum"),
        default=JobStatus.PENDING,
    )
    total_processed = Column(Integer, default=0)
    # FIX #10: Thêm 2 field để debug khi run fail
    error_log       = Column(Text, nullable=True)
    finished_at     = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=func.now())


class KpiRawMetric(Base):
    __tablename__ = "kpi_raw_metrics"
    __table_args__ = (
        UniqueConstraint(
            "teacher_id", "period", "source_module",
            name="uix_kpi_raw_sync",
        ),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id    = Column(UUID(as_uuid=True), nullable=False)
    period        = Column(String(7), nullable=False)
    source_module = Column(String(50), nullable=False)
    metric_data   = Column(JSON, nullable=False)
    synced_at     = Column(DateTime, default=func.now())


class KpiDispute(Base):
    __tablename__ = "kpi_disputes"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_id          = Column(UUID(as_uuid=True), ForeignKey("teacher_monthly_kpis.id"), nullable=False)
    teacher_id      = Column(UUID(as_uuid=True), nullable=False)
    reason          = Column(Text, nullable=False)
    status          = Column(
        Enum(DisputeStatus, native_enum=True, name="dispute_status_enum"),
        default=DisputeStatus.PENDING,
    )
    resolved_by     = Column(UUID(as_uuid=True), nullable=True)
    resolution_note = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=func.now())
    resolved_at     = Column(DateTime, nullable=True)


class Salary(Base):
    __tablename__ = "salaries"
    __table_args__ = (
        UniqueConstraint("teacher_id", "period", name="uix_teacher_salary_period"),
        CheckConstraint("base_salary_calc >= 0",  name="check_base_salary_calc"),
        CheckConstraint("kpi_bonus_calc >= 0",    name="check_kpi_bonus_calc"),
        CheckConstraint("lesson_count >= 0",      name="check_lesson_count"),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id       = Column(UUID(as_uuid=True), nullable=False)
    period           = Column(String(7), nullable=False)
    contract_type    = Column(
        Enum(ContractType, native_enum=True, name="salary_contract_type_enum"),
        nullable=False,
    )
    lesson_count      = Column(Integer, default=0)
    base_salary_calc  = Column(Numeric(15, 2), default=0)
    kpi_bonus_calc    = Column(Numeric(15, 2), default=0)
    fixed_allowance   = Column(Numeric(15, 2), default=0)
    total_adjustments = Column(Numeric(15, 2), default=0)
    net_salary        = Column(Numeric(15, 2), nullable=False)
    status            = Column(
        Enum(SalaryStatus, native_enum=True, name="salary_status_enum"),
        default=SalaryStatus.DRAFT,
    )
    approved_by  = Column(UUID(as_uuid=True), nullable=True)
    approved_at  = Column(DateTime, nullable=True)


class SalaryAdjustment(Base):
    __tablename__ = "salary_adjustments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="check_adjustment_amount_positive"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    salary_id       = Column(UUID(as_uuid=True), ForeignKey("salaries.id"), nullable=False)
    adjustment_type = Column(
        Enum(AdjustmentType, native_enum=True, name="adjustment_type_enum"),
        nullable=False,
    )
    amount     = Column(Numeric(15, 2), nullable=False)
    reason     = Column(String(255), nullable=False)
    created_by = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime, default=func.now())