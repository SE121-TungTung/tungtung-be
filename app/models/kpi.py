import enum
import uuid
from sqlalchemy import (
    Column, Integer, String, Numeric, ForeignKey, JSON, Boolean,
    DateTime, Date, CheckConstraint, UniqueConstraint, Enum, Text
)
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


# ---------------------------------------------------------------------------
# Enums (kept from old system)
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
# New Enums for Lotus KPI
# ---------------------------------------------------------------------------

class MetricUnit(str, enum.Enum):
    PERCENT = "%"
    SCORE   = "score"
    COUNT   = "count"
    STUDENT = "student"


class ApprovalStatus(str, enum.Enum):
    DRAFT     = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED  = "APPROVED"
    REJECTED  = "REJECTED"


class DataSource(str, enum.Enum):
    MANUAL     = "MANUAL"
    AUTO_SYNC  = "AUTO_SYNC"
    CALCULATED = "CALCULATED"


class PeriodType(str, enum.Enum):
    SEMESTER  = "SEMESTER"
    MONTHLY   = "MONTHLY"
    QUARTERLY = "QUARTERLY"


class BonusType(str, enum.Enum):
    FIXED_PER_PERIOD = "FIXED_PER_PERIOD"
    PER_HOUR         = "PER_HOUR"


class ApprovalAction(str, enum.Enum):
    SUBMIT           = "SUBMIT"
    APPROVE          = "APPROVE"
    REJECT           = "REJECT"
    REQUEST_REVISION = "REQUEST_REVISION"


# ---------------------------------------------------------------------------
# New Models — Lotus KPI Template System
# ---------------------------------------------------------------------------

class KPITemplate(Base):
    """Bộ cấu hình KPI (1 bộ cho GV, 1 bộ cho TA)."""
    __tablename__ = "kpi_templates"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name            = Column(String(200), nullable=False)
    # Use contract_type to distinguish GV vs TA templates
    contract_type   = Column(
        Enum(ContractType, native_enum=False, name="kpi_template_contract_type"),
        nullable=False,
    )
    max_bonus_amount = Column(Numeric(15, 2), nullable=False, default=0)
    bonus_type      = Column(
        Enum(BonusType, native_enum=False, name="kpi_template_bonus_type"),
        default=BonusType.FIXED_PER_PERIOD,
    )
    version         = Column(Integer, nullable=False, default=1)
    effective_from  = Column(Date, nullable=True)
    is_active       = Column(Boolean, default=True)
    description     = Column(Text, nullable=True)
    created_by      = Column(UUID(as_uuid=True), nullable=True)
    created_at      = Column(DateTime, default=func.now())
    updated_at      = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    metrics = relationship("KPITemplateMetric", back_populates="template",
                           order_by="KPITemplateMetric.sort_order",
                           cascade="all, delete-orphan")


class KPITemplateMetric(Base):
    """Từng chỉ tiêu trong template (A1, A2, ... D3)."""
    __tablename__ = "kpi_template_metrics"
    __table_args__ = (
        UniqueConstraint("template_id", "metric_code", name="uix_template_metric_code"),
    )

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id    = Column(UUID(as_uuid=True), ForeignKey("kpi_templates.id", ondelete="CASCADE"), nullable=False)
    metric_code    = Column(String(10), nullable=False)   # 'A', 'A1', 'B', 'B1'...
    metric_name    = Column(String(255), nullable=False)
    is_group_header = Column(Boolean, default=False)       # True for group rows (A, B, C, D)
    unit           = Column(
        Enum(MetricUnit, native_enum=False, name="kpi_metric_unit"),
        nullable=True,  # Null for group headers
    )
    target_min     = Column(Numeric(10, 4), nullable=True)
    target_max     = Column(Numeric(10, 4), nullable=True)
    weight         = Column(Numeric(5, 4), nullable=True)  # e.g. 0.30 = 30% of group
    group_weight   = Column(Numeric(5, 4), nullable=True)  # Group-level weight (e.g. 0.4 for group A)
    sort_order     = Column(Integer, nullable=False, default=0)
    description    = Column(Text, nullable=True)

    # Relationships
    template = relationship("KPITemplate", back_populates="metrics")


class KPIPeriod(Base):
    """Kỳ KPI (kỳ học, tháng, quý...)."""
    __tablename__ = "kpi_periods"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name        = Column(String(100), nullable=False)        # "Kỳ 1 - 2025"
    period_type = Column(
        Enum(PeriodType, native_enum=False, name="kpi_period_type"),
        default=PeriodType.SEMESTER,
    )
    start_date  = Column(Date, nullable=False)
    end_date    = Column(Date, nullable=False)
    is_active   = Column(Boolean, default=True)
    created_by  = Column(UUID(as_uuid=True), nullable=True)
    created_at  = Column(DateTime, default=func.now())

    # Relationships
    records = relationship("KPIRecord", back_populates="period")


class KPIRecord(Base):
    """Bản ghi KPI của 1 nhân viên trong 1 kỳ."""
    __tablename__ = "kpi_records"
    __table_args__ = (
        UniqueConstraint("staff_id", "period_id", name="uix_staff_period"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    staff_id        = Column(UUID(as_uuid=True), nullable=False)   # FK to users.id
    period_id       = Column(UUID(as_uuid=True), ForeignKey("kpi_periods.id"), nullable=False)
    template_id     = Column(UUID(as_uuid=True), ForeignKey("kpi_templates.id"), nullable=False)
    total_score     = Column(Numeric(5, 4), nullable=True)         # 0.0000 → 1.0000
    bonus_amount    = Column(Numeric(15, 2), nullable=True)        # VND
    teaching_hours  = Column(Numeric(8, 2), nullable=True)         # Auto-calculated, adjustable
    approval_status = Column(
        Enum(ApprovalStatus, native_enum=False, name="kpi_approval_status"),
        default=ApprovalStatus.DRAFT,
    )
    submitted_at    = Column(DateTime, nullable=True)
    approved_by     = Column(UUID(as_uuid=True), nullable=True)
    approved_at     = Column(DateTime, nullable=True)
    rejection_note  = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=func.now())
    updated_at      = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    period         = relationship("KPIPeriod", back_populates="records")
    template       = relationship("KPITemplate")
    metric_results = relationship("KPIMetricResult", back_populates="record",
                                  cascade="all, delete-orphan")
    approval_logs  = relationship("KPIApprovalLog", back_populates="record",
                                  order_by="KPIApprovalLog.created_at",
                                  cascade="all, delete-orphan")
    support_calcs  = relationship("SupportCalcEntry", back_populates="record",
                                  cascade="all, delete-orphan")
    disputes       = relationship("KpiDispute", back_populates="record")


class KPIMetricResult(Base):
    """Kết quả từng chỉ tiêu trong 1 bản ghi."""
    __tablename__ = "kpi_metric_results"
    __table_args__ = (
        UniqueConstraint("kpi_record_id", "metric_id", name="uix_record_metric"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_record_id   = Column(UUID(as_uuid=True), ForeignKey("kpi_records.id", ondelete="CASCADE"), nullable=False)
    metric_id       = Column(UUID(as_uuid=True), ForeignKey("kpi_template_metrics.id"), nullable=False)
    actual_value    = Column(Numeric(10, 4), nullable=True)
    converted_score = Column(Numeric(5, 4), nullable=True)
    data_source     = Column(
        Enum(DataSource, native_enum=False, name="kpi_data_source"),
        default=DataSource.MANUAL,
    )
    support_calc_id = Column(UUID(as_uuid=True), ForeignKey("support_calc_entries.id"), nullable=True)
    note            = Column(Text, nullable=True)

    # Relationships
    record          = relationship("KPIRecord", back_populates="metric_results")
    metric          = relationship("KPITemplateMetric")
    support_calc    = relationship("SupportCalcEntry", foreign_keys=[support_calc_id])


class KPIApprovalLog(Base):
    """Lịch sử duyệt/từ chối."""
    __tablename__ = "kpi_approval_logs"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_record_id  = Column(UUID(as_uuid=True), ForeignKey("kpi_records.id", ondelete="CASCADE"), nullable=False)
    action         = Column(
        Enum(ApprovalAction, native_enum=False, name="kpi_approval_action"),
        nullable=False,
    )
    actor_id       = Column(UUID(as_uuid=True), nullable=False)
    comment        = Column(Text, nullable=True)
    created_at     = Column(DateTime, default=func.now())

    # Relationships
    record = relationship("KPIRecord", back_populates="approval_logs")


class SupportCalcEntry(Base):
    """Lưu dữ liệu sheet 'Công cụ hỗ trợ' (tính A1/A2)."""
    __tablename__ = "support_calc_entries"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_record_id   = Column(UUID(as_uuid=True), ForeignKey("kpi_records.id", ondelete="CASCADE"), nullable=False)
    class_name      = Column(String(100), nullable=True)    # Tên lớp (optional)
    class_size      = Column(Integer, nullable=False)
    max_score       = Column(Numeric(5, 2), nullable=False)
    avg_threshold   = Column(Numeric(5, 2), nullable=False)
    above_avg_count = Column(Integer, nullable=False)        # Không tính HS đạt điểm cao
    high_threshold  = Column(Numeric(5, 2), nullable=False)
    above_high_count = Column(Integer, nullable=False)
    rate_above_avg  = Column(Numeric(5, 4), nullable=False)  # Output → A1
    rate_above_high = Column(Numeric(5, 4), nullable=False)  # Output → A2
    created_at      = Column(DateTime, default=func.now())

    # Relationships
    record = relationship("KPIRecord", back_populates="support_calcs")


# ---------------------------------------------------------------------------
# Deprecated Models (kept for backward compatibility with existing payroll data)
# ---------------------------------------------------------------------------

class KpiTier(Base):
    """DEPRECATED: Use KPITemplate + KPITemplateMetric instead."""
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
    reward_per_lesson  = Column(Numeric(15, 2), default=0)
    status             = Column(
        Enum(ActiveStatus, native_enum=True, name="kpi_tier_status_enum"),
        default=ActiveStatus.ACTIVE,
    )


class KpiCriteria(Base):
    """DEPRECATED: Use KPITemplateMetric instead."""
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
    """DEPRECATED: Use KPIRecord instead."""
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
    """DEPRECATED: Calculation is now per-record via KPIRecord."""
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


class PayrollRun(Base):
    __tablename__ = "payroll_runs"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period          = Column(String(7), unique=True, nullable=False)
    status          = Column(
        Enum(JobStatus, native_enum=True, name="payroll_run_status_enum"),
        default=JobStatus.PENDING,
    )
    total_processed = Column(Integer, default=0)
    error_log       = Column(Text, nullable=True)
    finished_at     = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=func.now())


class KpiRawMetric(Base):
    """DEPRECATED: Use KPIMetricResult with data_source instead."""
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
    """Migrated to reference KPIRecord instead of TeacherMonthlyKpi."""
    __tablename__ = "kpi_disputes"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # New FK pointing to kpi_records
    kpi_record_id   = Column(UUID(as_uuid=True), ForeignKey("kpi_records.id"), nullable=True)
    # Keep old FK for backward compat with existing data
    kpi_id          = Column(UUID(as_uuid=True), ForeignKey("teacher_monthly_kpis.id"), nullable=True)
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

    # Relationships
    record = relationship("KPIRecord", back_populates="disputes")


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