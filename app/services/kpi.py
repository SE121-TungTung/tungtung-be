from sqlalchemy import case, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
from uuid import UUID
from fastapi import HTTPException, status, BackgroundTasks
from datetime import datetime, timedelta
from decimal import Decimal
import logging

from app.core.database import SessionLocal
from app.core.exceptions import APIException
from app.models.kpi import (
    DisputeStatus, KpiDispute, KpiTier, KpiCriteria, KpiCalculationJob,
    TeacherMonthlyKpi, TeacherPayrollConfig,
    JobStatus, ContractType,
)
from app.models.user import User, UserRole
from app.models.session_attendance import ClassSession, SessionStatus
from app.schemas.kpi import KpiTierUpdate, KpiCalculationJobCreate, KpiDisputeCreate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# KpiSettingsService
# ---------------------------------------------------------------------------
class KpiSettingsService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_tiers(self) -> List[KpiTier]:
        return self.db.query(KpiTier).order_by(KpiTier.min_score.asc()).all()

    def bulk_update_tiers(self, tiers_payload: List[KpiTierUpdate]) -> List[KpiTier]:
        if not tiers_payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dữ liệu cấu hình trống",
            )

        sorted_tiers = sorted(tiers_payload, key=lambda x: x.min_score)

        if sorted_tiers[0].min_score != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bậc đầu tiên phải có min_score = 0",
            )
        if sorted_tiers[-1].max_score != 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bậc cuối cùng phải có max_score = 100",
            )

        for i, current in enumerate(sorted_tiers):
            if current.min_score >= current.max_score:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Bậc '{current.tier_name}': min_score phải nhỏ hơn max_score",
                )

            if i < len(sorted_tiers) - 1:
                next_tier = sorted_tiers[i + 1]
                if current.max_score > next_tier.min_score:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Chồng chéo điểm giữa bậc '{current.tier_name}' "
                            f"và '{next_tier.tier_name}'"
                        ),
                    )
                if current.max_score < next_tier.min_score:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Khoảng trống điểm giữa bậc '{current.tier_name}' "
                            f"và '{next_tier.tier_name}'"
                        ),
                    )
        existing_ids = {t.id for t in self.db.query(KpiTier.id).all()}
        payload_ids  = {t.id for t in sorted_tiers if t.id is not None}
        ids_to_delete = existing_ids - payload_ids

        # Check FK trước khi xóa
        for del_id in ids_to_delete:
            in_use = self.db.query(TeacherMonthlyKpi).filter(
                TeacherMonthlyKpi.kpi_tier_id == del_id
            ).first()
            if in_use:
                raise HTTPException(
                    status_code=409,
                    detail=f"Bậc KPI (ID={del_id}) đang được sử dụng, không thể xóa"
                )

        try:
            # Cập nhật hoặc Thêm mới
            new_tiers = []
            for tier_data in sorted_tiers:
                data_dict = tier_data.model_dump(exclude={"id"})
                if tier_data.id and tier_data.id in existing_ids:
                    self.db.query(KpiTier).filter(KpiTier.id == tier_data.id).update(data_dict)
                else:
                    new_tier = KpiTier(**data_dict)
                    self.db.add(new_tier)
                    new_tiers.append(new_tier)

            # Xóa các id không còn trong cấu hình
            for del_id in ids_to_delete:
                self.db.query(KpiTier).filter(KpiTier.id == del_id).delete()

            self.db.commit()
            return self.db.query(KpiTier).order_by(KpiTier.min_score.asc()).all()
        except Exception as e:
            self.db.rollback()
            logger.error(f"bulk_update_tiers failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                code="INTERNAL_SERVER_ERROR",
                message="Đã có lỗi xảy ra khi cập nhật cấu hình bậc KPI",
            )

# ---------------------------------------------------------------------------
# KpiCriteriaService
# ---------------------------------------------------------------------------
class KpiCriteriaService:
    def __init__(self, db: Session):
        self.db = db

    def validate_total_weight(self, criteria_list) -> None:
        total = sum(Decimal(str(c.weight_percent)) for c in criteria_list)
        if total != Decimal("100"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tổng trọng số tiêu chí KPI phải bằng 100%. Hiện tại: {total}%",
            )

# ---------------------------------------------------------------------------
# DisputeService (Bổ sung fix BUG-01)
# ---------------------------------------------------------------------------
class KpiDisputeService:
    def __init__(self, db: Session):
        self.db = db

    def create_dispute(self, teacher_id: UUID, payload: KpiDisputeCreate):
        kpi_record = self.db.query(TeacherMonthlyKpi).filter(
            TeacherMonthlyKpi.id == payload.kpi_id,
            TeacherMonthlyKpi.teacher_id == teacher_id
        ).first()

        if not kpi_record:
            raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu KPI")

        # Nghiệp vụ: Chỉ chấp nhận xử lý dispute khi bảng KPI đang trong trạng thái "draft" (hoặc tương đương)
        # và không quá deadline 48 giờ.
        if not kpi_record.finalized_at:
            raise HTTPException(status_code=403, detail="KPI chưa được chốt, không thể khiếu nại")

        if hasattr(kpi_record, "status") and kpi_record.status != "draft":
            raise HTTPException(status_code=403, detail="Bảng KPI đã chốt, không thể khiếu nại")

        if hasattr(kpi_record, "finalized_at") and datetime.now() > kpi_record.finalized_at + timedelta(hours=48):
            raise HTTPException(status_code=403, detail="Hết thời hạn khiếu nại (48h sau khi chốt dữ liệu tạm tính)")

        # ... Create dispute logic
        # Check không tạo duplicate dispute cho cùng kpi_id đang xử lý
        existing = self.db.query(KpiDispute).filter(
            KpiDispute.kpi_id == payload.kpi_id,
            KpiDispute.teacher_id == teacher_id,
            KpiDispute.status == DisputeStatus.PENDING,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Đã có khiếu nại đang xử lý cho KPI này")

        dispute = KpiDispute(
            kpi_id=payload.kpi_id,
            teacher_id=teacher_id,
            reason=payload.reason,
            status=DisputeStatus.PENDING,
        )
        self.db.add(dispute)
        self.db.commit()
        self.db.refresh(dispute)
        return dispute

# ---------------------------------------------------------------------------
# KpiCalculationService
# ---------------------------------------------------------------------------
class KpiCalculationService:
    def __init__(self, db: Session):
        self.db = db

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

        bg_tasks.add_task(self._execute_calculation, new_job.job_id, payload.period)

        return {
            "job_id": new_job.job_id,
            "period": payload.period,
            "status": JobStatus.PENDING,
            "total_teachers": 0,
            "processed_count": 0,
            "started_at": new_job.started_at,
        }

    def _execute_calculation(self, job_id: UUID, period: str) -> None:
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

            is_force_calc = current_job.payload.get("force", False) if hasattr(current_job, "payload") else False

            for i, teacher in enumerate(teachers):
                try:
                    self._calculate_teacher_kpi(db, teacher.id, period, force=is_force_calc)
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

        # Gọi validate dead code
        criteria_list = db.query(KpiCriteria).filter(KpiCriteria.status == "ACTIVE").all()
        criteria_service = KpiCriteriaService(db)
        criteria_service.validate_total_weight(criteria_list)

        payroll_config: TeacherPayrollConfig | None = db.query(TeacherPayrollConfig).filter(
            TeacherPayrollConfig.teacher_id == teacher_id
        ).first()

        if not payroll_config:
            raise ValueError(f"Không tìm thấy cấu hình lương cho giáo viên {teacher_id}")

        criteria_list = db.query(KpiCriteria).filter(KpiCriteria.status == "ACTIVE").all()

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
            raise NotImplementedError("Criteria LESSON_COMPLETION chưa có data source")

        elif criteria_code == "STUDENT_SATISFACTION":
            raise NotImplementedError("Criteria STUDENT_SATISFACTION chưa có data source")

        elif criteria_code == "ACADEMIC_QUALITY":
            raise NotImplementedError("Criteria ACADEMIC_QUALITY chưa có data source")

        else:
            raise NotImplementedError(f"Criteria '{criteria_code}' chưa có data source")
        
class SalaryService:
    def __init__(self, db: Session):
        self.db = db

    def get_salary(self, salary_id: UUID, current_user: User):
        from app.models.kpi import Salary # Giả định import
        salary = self.db.query(Salary).filter(Salary.id == salary_id).first()
        if not salary:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiếu lương")

        if salary.teacher_id != current_user.id and current_user.role != "admin_center":
            raise HTTPException(status_code=403, detail="Không có quyền xem phiếu lương này")

        return salary