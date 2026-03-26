from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, JSON, DateTime, CheckConstraint, UniqueConstraint, Enum, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
import enum
import uuid

Base = declarative_base()

class ContractType(str, enum.Enum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    NATIVE = "NATIVE"

class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class ActiveStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

# --- Models ---
class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    setting_key = Column(String(50), unique=True, nullable=False)
    setting_value = Column(String(255), nullable=False)
    description = Column(String(255), nullable=True)

class KpiTier(Base):
    __tablename__ = "kpi_tiers"
    __table_args__ = (
        CheckConstraint('min_score >= 0', name='check_min_score_positive'),
        CheckConstraint('max_score <= 100', name='check_max_score_limit'),
        CheckConstraint('min_score < max_score', name='check_min_less_than_max'),
        CheckConstraint('reward_percentage >= 0', name='check_reward_positive'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tier_name = Column(String(20), nullable=False, unique=True)
    min_score = Column(Numeric(5, 2), nullable=False)
    max_score = Column(Numeric(5, 2), nullable=False)
    reward_percentage = Column(Numeric(5, 2), nullable=False)
    status = Column(
        Enum(ActiveStatus, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='active_status_enum'), 
        default=ActiveStatus.ACTIVE
    )

class KpiCriteria(Base):
    __tablename__ = "kpi_criterias"
    __table_args__ = (
        CheckConstraint('weight_percent > 0', name='check_weight_positive'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    criteria_code = Column(String(50), unique=True, nullable=False)
    criteria_name = Column(String(100), nullable=False)
    weight_percent = Column(Numeric(5, 2), nullable=False)
    status = Column(
        Enum(ActiveStatus, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='active_status_enum'), 
        default=ActiveStatus.ACTIVE
    )

class TeacherPayrollConfig(Base):
    __tablename__ = "teacher_payroll_configs"
    __table_args__ = (
        CheckConstraint('base_salary >= 0', name='check_base_salary'),
        CheckConstraint('lesson_rate >= 0', name='check_lesson_rate'),
        CheckConstraint('max_kpi_bonus >= 0', name='check_max_kpi_bonus'),
    )

    teacher_id = Column(UUID(as_uuid=True), primary_key=True) 
    contract_type = Column(
        Enum(ContractType, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='contract_type_enum'), 
        nullable=False
    )
    base_salary = Column(Numeric(15, 2), default=0)
    lesson_rate = Column(Numeric(15, 2), default=0)
    max_kpi_bonus = Column(Numeric(15, 2), default=0)
    fixed_allowance = Column(Numeric(15, 2), default=0)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class TeacherMonthlyKpi(Base):
    __tablename__ = "teacher_monthly_kpis"
    __table_args__ = (
        UniqueConstraint('teacher_id', 'period', name='uix_teacher_period'),
        CheckConstraint('total_score >= 0 AND total_score <= 100', name='check_total_score'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    teacher_id = Column(UUID(as_uuid=True), nullable=False)
    period = Column(String(7), nullable=False) 
    total_score = Column(Numeric(5, 2), nullable=False)
    kpi_tier_id = Column(Integer, ForeignKey('kpi_tiers.id'))
    kpi_details = Column(JSON, nullable=False)
    calculated_bonus = Column(Numeric(15, 2), default=0)
    created_at = Column(DateTime, default=func.now())

class KpiCalculationJob(Base):
    __tablename__ = "kpi_calculation_jobs"

    # Đã đổi thành kiểu UUID chuẩn của PostgreSQL
    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period = Column(String(7), nullable=False)
    status = Column(
        Enum(JobStatus, values_callable=lambda obj: [e.value for e in obj], native_enum=True, name='job_status_enum'), 
        default=JobStatus.PENDING
    )
    total_teachers = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    error_log = Column(Text, nullable=True)
    started_at = Column(DateTime, default=func.now())
    finished_at = Column(DateTime, nullable=True)