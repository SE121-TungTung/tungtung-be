from sqlalchemy import case, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException, status, BackgroundTasks
from datetime import datetime
from decimal import Decimal
import logging

from app.core.database import SessionLocal
from app.core.exceptions import APIException
from app.models.kpi import (
    KpiTier, KpiCriteria, KpiCalculationJob,
    TeacherMonthlyKpi, TeacherPayrollConfig,
    JobStatus, ContractType,
)
from app.models.user import User, UserRole
from app.models.session_attendance import ClassSession, SessionStatus
from app.schemas.kpi import KpiCalculationJobCreate
from app.services.kpi.settings_service import KpiCriteriaService

logger = logging.getLogger(__name__)

class KpiCalculationService:
    def __init__(self, db: Session):
        self.db = db

    def get_job(self, job_id: UUID) -> KpiCalculationJob:
        job = self.db.query(KpiCalculationJob).filter(KpiCalculationJob.job_id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Không tìm thấy tiến trình tính toán")
        return job

    def get_teacher_kpi(self, teacher_id: UUID, period: str) -> TeacherMonthlyKpi:
        kpi = self.db.query(TeacherMonthlyKpi).filter(
            TeacherMonthlyKpi.teacher_id == teacher_id,
            TeacherMonthlyKpi.period == period,
        ).first()
        if not kpi:
            raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu KPI của giáo viên trong kỳ này")
        return kpi

    def trigger_calculation_job(
        self,
        payload: KpiCalculationJobCreate,
        bg_tasks: BackgroundTasks,
    ) -> dict:
        existing_job = self.db.query(KpiCalculationJob).filter(
            KpiCalculationJob.period == payload.period,
            KpiCalculationJob.status.in_([JobStatus.PENDING, JobStatus.PROCESSING]),
        ).first()

        if existing_job:
            raise APIException(
                status_code=409,
                code="JOB_ALREADY_EXISTS",
                message=f"Tiến trình tính KPI cho kỳ {payload.period} đang diễn ra.",
            )

        try:
            new_job = KpiCalculationJob(period=payload.period, status=JobStatus.PENDING)
            self.db.add(new_job)
            self.db.commit()
            self.db.refresh(new_job)
        except IntegrityError:
            self.db.rollback()
            raise APIException(
                status_code=409,
                code="JOB_ALREADY_EXISTS",
                message=f"Tiến trình tính KPI cho kỳ {payload.period} đã tồn tại.",
            )

        # Trích xuất biến force để tính lại, do payload của ta là Pydantic model
        force = getattr(payload, "force", False)

        bg_tasks.add_task(self._execute_calculation, new_job.job_id, payload.period, force)

        return {
            "job_id": new_job.job_id,
            "period": payload.period,
            "status": JobStatus.PENDING,
            "total_teachers": 0,
            "processed_count": 0,
            "started_at": new_job.started_at,
        }

    def _execute_calculation(self, job_id: UUID, period: str, force: bool = False) -> None:
        db = SessionLocal()
        try:
            current_job = db.query(KpiCalculationJob).filter(
                KpiCalculationJob.job_id == job_id
            ).first()

            if not current_job:
                logger.error(f"KPI Calculation Job {job_id} not found")
                return

            current_job.status = JobStatus.PROCESSING
            db.commit()

            teachers = db.query(User).filter(User.role == UserRole.TEACHER).all()
            current_job.total_teachers = len(teachers)
            db.commit()

            processed_count = 0
            errors: List[str] = []

            for i, teacher in enumerate(teachers):
                try:
                    self._calculate_teacher_kpi(db, teacher.id, period, force=force)
                    processed_count += 1
                except Exception as e:
                    error_msg = f"Teacher {teacher.id}: {str(e)}"
                    logger.error(f"KPI calc error — {error_msg}")
                    errors.append(error_msg)

                if (i + 1) % 5 == 0 or (i + 1) == len(teachers):
                    current_job.processed_count = processed_count
                    db.commit()

            current_job.status = JobStatus.COMPLETED
            current_job.finished_at = datetime.utcnow()
            if errors:
                current_job.error_log = "\n".join(errors)
            db.commit()

            logger.info(
                f"KPI Job {job_id} completed. Processed {processed_count}/{len(teachers)} teachers."
            )

        except Exception as e:
            logger.error(f"KPI Job {job_id} failed: {e}", exc_info=True)
            try:
                current_job = db.query(KpiCalculationJob).filter(
                    KpiCalculationJob.job_id == job_id
                ).first()
                if current_job:
                    current_job.status = JobStatus.FAILED
                    current_job.error_log = str(e)
                    current_job.finished_at = datetime.utcnow()
                    db.commit()
            except Exception:
                pass
        finally:
            db.close()

    def _calculate_teacher_kpi(self, db: Session, teacher_id: UUID, period: str, force: bool) -> None:
        existing = db.query(TeacherMonthlyKpi).filter(
            TeacherMonthlyKpi.teacher_id == teacher_id,
            TeacherMonthlyKpi.period == period,
        ).first()
        if existing:
            if not force:
                return
            # Xóa bản ghi cũ nếu force=True để tính lại
            db.delete(existing)
            db.flush()

        criteria_list = db.query(KpiCriteria).filter(KpiCriteria.status == "ACTIVE").all()
        criteria_service = KpiCriteriaService(db)
        criteria_service.validate_total_weight(criteria_list)

        payroll_config: TeacherPayrollConfig | None = db.query(TeacherPayrollConfig).filter(
            TeacherPayrollConfig.teacher_id == teacher_id
        ).first()

        if not payroll_config:
            raise ValueError(f"Không tìm thấy cấu hình lương cho giáo viên {teacher_id}")

        criteria_scores = []
        total_score = Decimal(0)

        for criteria in criteria_list:
            score = self._calculate_criteria_score(db, teacher_id, period, criteria)
            weight = Decimal(str(criteria.weight_percent))

            criteria_scores.append({
                "code":      criteria.criteria_code,
                "score":     float(score),
                "max_score": 100.0,
            })

            total_score += score * weight / Decimal(100)

        total_score_rounded = total_score.quantize(Decimal("0.01"))

        kpi_tier: KpiTier | None = db.query(KpiTier).filter(
            KpiTier.min_score <= total_score_rounded,
            KpiTier.max_score >= total_score_rounded,
        ).first()

        calculated_bonus = self._calculate_bonus(payroll_config, kpi_tier, db, teacher_id, period)

        teacher_kpi = TeacherMonthlyKpi(
            teacher_id       = teacher_id,
            period           = period,
            total_score      = total_score_rounded,
            kpi_tier_id      = kpi_tier.id if kpi_tier else None,
            kpi_details      = {"criteria_scores": criteria_scores},
            calculated_bonus = calculated_bonus,
        )
        db.add(teacher_kpi)
        db.commit()
        db.refresh(teacher_kpi)

    def _calculate_bonus(
        self,
        payroll_config: TeacherPayrollConfig,
        kpi_tier: KpiTier | None,
        db: Session,
        teacher_id: UUID,
        period: str,
    ) -> Decimal:
        if not kpi_tier:
            return Decimal(0)

        contract_type = payroll_config.contract_type

        if contract_type == ContractType.FULL_TIME:
            if not payroll_config.max_kpi_bonus:
                return Decimal(0)
            bonus_pct = Decimal(str(kpi_tier.reward_percentage))
            return Decimal(str(payroll_config.max_kpi_bonus)) * bonus_pct / Decimal(100)

        elif contract_type in (ContractType.PART_TIME, ContractType.NATIVE):
            lesson_count = self._get_lesson_count(db, teacher_id, period)
            reward_per_lesson = Decimal(str(kpi_tier.reward_per_lesson or 0))
            return Decimal(lesson_count) * reward_per_lesson

        return Decimal(0)

    def _get_lesson_count(self, db: Session, teacher_id: UUID, period: str) -> int:
        period_year, period_month = period.split("-")
        return (
            db.query(ClassSession)
            .filter(
                ClassSession.teacher_id == teacher_id,
                ClassSession.status == SessionStatus.COMPLETED,
                func.extract("year",  ClassSession.session_date) == int(period_year),
                func.extract("month", ClassSession.session_date) == int(period_month),
            )
            .count()
        )

    def _calculate_criteria_score(
        self, db: Session, teacher_id: UUID, period: str, criteria
    ) -> Decimal:
        criteria_code = criteria.criteria_code
        period_year, period_month = period.split("-")

        if criteria_code == "ATTENDANCE":
            base_filter = [
                ClassSession.teacher_id == teacher_id,
                func.extract("year",  ClassSession.session_date) == int(period_year),
                func.extract("month", ClassSession.session_date) == int(period_month),
                ClassSession.status != SessionStatus.CANCELLED  # Lọc bỏ CANCELLED
            ]

            result = db.query(
                func.count().label("scheduled"),
                func.count(case((ClassSession.status == SessionStatus.COMPLETED, 1))).label("completed")
            ).filter(*base_filter).one()

            scheduled = result.scheduled
            completed = result.completed

            if scheduled > 0:
                score = Decimal(completed) / Decimal(scheduled) * Decimal(100)
            else:
                score = Decimal(100)

            return min(score, Decimal(100))

        elif criteria_code == "LESSON_COMPLETION":
            # Ghi chú: Có thể cần phát triển
            return Decimal(100)

        elif criteria_code == "STUDENT_SATISFACTION":
            # Ghi chú: Có thể cần phát triển
            return Decimal(100)

        elif criteria_code == "ACADEMIC_QUALITY":
            # Ghi chú: Có thể cần phát triển
            return Decimal(100)

        else:
            return Decimal(100)
