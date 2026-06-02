from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from typing import List, Tuple
from uuid import UUID
from fastapi import HTTPException, BackgroundTasks
from datetime import datetime
from decimal import Decimal

from app.models.kpi import (
    Salary, SalaryStatus, SalaryAdjustment, AdjustmentType,
    TeacherPayrollConfig, PayrollRun, JobStatus, ContractType,
    KPIRecord, KPIPeriod, ApprovalStatus,
)
from app.models.user import User, UserRole
from app.schemas.kpi import SalaryAdjustmentCreate, TeacherPayrollConfigUpdate, PayrollRunCreate

class SalaryService:
    def get_salary(self, db: Session, salary_id: UUID, current_user: User) -> Salary:
        salary = db.query(Salary).filter(Salary.id == salary_id).first()
        if not salary:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiếu lương")

        if salary.teacher_id != current_user.id and current_user.role != UserRole.CENTER_ADMIN:
            raise HTTPException(status_code=403, detail="Không có quyền xem phiếu lương này")

        return salary

    def _enrich_with_teacher_name(self, db: Session, salaries: list[Salary]) -> list[dict]:
        """Attach teacher_name to each salary record."""
        if not salaries:
            return []
        teacher_ids = list({s.teacher_id for s in salaries})
        teachers = db.query(User.id, User.first_name, User.last_name).filter(User.id.in_(teacher_ids)).all()
        name_map = {t.id: f"{t.last_name} {t.first_name}" for t in teachers}
        results = []
        for s in salaries:
            from app.schemas.kpi import SalaryResponse
            data = SalaryResponse.model_validate(s)
            data.teacher_name = name_map.get(s.teacher_id)
            results.append(data)
        return results

    def get_history(self, db: Session, teacher_id: UUID, period: str | None, page: int, limit: int) -> Tuple[list, int]:
        query = db.query(Salary).filter(Salary.teacher_id == teacher_id)
        if period:
            query = query.filter(Salary.period == period)
            
        total = query.count()
        salaries = query.order_by(Salary.period.desc()).offset((page - 1) * limit).limit(limit).all()
        return self._enrich_with_teacher_name(db, salaries), total

    def get_all(self, db: Session, period: str | None, page: int, limit: int) -> Tuple[list, int]:
        query = db.query(Salary)
        if period:
            query = query.filter(Salary.period == period)
            
        total = query.count()
        salaries = query.order_by(Salary.period.desc()).offset((page - 1) * limit).limit(limit).all()
        return self._enrich_with_teacher_name(db, salaries), total

    def approve(self, db: Session, salary_id: UUID, admin_id: UUID) -> Salary:
        salary = db.query(Salary).filter(Salary.id == salary_id).first()
        if not salary:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiếu lương")
            
        if salary.status != SalaryStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Chỉ có thể duyệt phiếu lương đang ở trạng thái DRAFT")

        salary.status = SalaryStatus.APPROVED
        salary.approved_by = admin_id
        salary.approved_at = datetime.now()
        
        db.commit()
        db.refresh(salary)
        return salary

    def add_adjustment(self, db: Session, salary_id: UUID, payload: SalaryAdjustmentCreate, admin_id: UUID) -> SalaryAdjustment:
        salary = db.query(Salary).filter(Salary.id == salary_id).first()
        if not salary:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiếu lương")
            
        if salary.status != SalaryStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Không thể điều chỉnh phiếu lương đã chốt/duyệt")

        # Cập nhật tổng điều chỉnh và net_salary của bảng lương
        amount_to_apply = payload.amount
        if payload.adjustment_type == AdjustmentType.DEDUCTION:
            amount_to_apply = -amount_to_apply

        salary.total_adjustments += Decimal(str(amount_to_apply))
        salary.net_salary += Decimal(str(amount_to_apply))

        adjustment = SalaryAdjustment(
            salary_id=salary_id,
            adjustment_type=payload.adjustment_type,
            amount=payload.amount,
            reason=payload.reason,
            created_by=admin_id,
        )
        db.add(adjustment)
        db.commit()
        db.refresh(adjustment)
        return adjustment


class TeacherPayrollConfigService:
    def get_config(self, db: Session, teacher_id: UUID) -> TeacherPayrollConfig:
        config = db.query(TeacherPayrollConfig).filter(
            TeacherPayrollConfig.teacher_id == teacher_id
        ).first()
        if not config:
            raise HTTPException(status_code=404, detail="Chưa có cấu hình lương cho giáo viên này")
        return config

    def update_config(self, db: Session, teacher_id: UUID, payload: TeacherPayrollConfigUpdate) -> TeacherPayrollConfig:
        config = db.query(TeacherPayrollConfig).filter(TeacherPayrollConfig.teacher_id == teacher_id).first()
        if config:
            config.contract_type = payload.contract_type
            config.base_salary = payload.base_salary
            config.lesson_rate = payload.lesson_rate
            config.max_kpi_bonus = payload.max_kpi_bonus
            config.fixed_allowance = payload.fixed_allowance
            config.updated_at = datetime.utcnow()
        else:
            config = TeacherPayrollConfig(
                teacher_id=teacher_id,
                contract_type=payload.contract_type,
                base_salary=payload.base_salary,
                lesson_rate=payload.lesson_rate,
                max_kpi_bonus=payload.max_kpi_bonus,
                fixed_allowance=payload.fixed_allowance,
            )
            db.add(config)
            
        db.commit()
        db.refresh(config)
        return config


class PayrollRunService:
    def create_run(self, db: Session, payload: PayrollRunCreate, bg_tasks: BackgroundTasks) -> PayrollRun:
        existing = db.query(PayrollRun).filter(PayrollRun.period == payload.period).first()
        if existing and existing.status in [JobStatus.PENDING, JobStatus.PROCESSING]:
            raise HTTPException(status_code=409, detail="Tiến trình tính lương đang chạy")
            
        if not existing:
            run = PayrollRun(period=payload.period, status=JobStatus.PENDING)
            db.add(run)
        else:
            run = existing
            run.status = JobStatus.PENDING
            run.error_log = None
            
        db.commit()
        db.refresh(run)

        bg_tasks.add_task(self._process_payroll, run.id, payload.period)
        return run

    def get_run(self, db: Session, run_id: UUID) -> PayrollRun:
        run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Không tìm thấy tiến trình tính lương")
        return run

    def list_runs(self, db: Session) -> list[PayrollRun]:
        return db.query(PayrollRun).order_by(PayrollRun.created_at.desc()).all()

    def _process_payroll(self, run_id: UUID, period: str):
        """
        Process payroll using KPIRecord (Lotus KPI system).

        The `period` param is a string like "2026-04".
        We find a KPIPeriod whose date range covers that month,
        then use approved KPIRecords from that period.
        """
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
            if not run:
                return

            run.status = JobStatus.PROCESSING
            db.commit()

            # Parse period string "YYYY-MM" to find matching KPIPeriod
            year, month = int(period[:4]), int(period[5:7])
            kpi_period = (
                db.query(KPIPeriod)
                .filter(
                    extract("year", KPIPeriod.start_date) <= year,
                    extract("year", KPIPeriod.end_date) >= year,
                    extract("month", KPIPeriod.start_date) <= month,
                    extract("month", KPIPeriod.end_date) >= month,
                )
                .first()
            )

            if not kpi_period:
                run.status = JobStatus.FAILED
                run.error_log = f"Không tìm thấy kỳ KPI cho period {period}"
                run.finished_at = datetime.utcnow()
                db.commit()
                return

            # Get approved KPI records for this period
            kpi_records = (
                db.query(KPIRecord)
                .filter(
                    KPIRecord.period_id == kpi_period.id,
                    KPIRecord.approval_status == ApprovalStatus.APPROVED,
                )
                .all()
            )

            processed = 0
            errors = []
            
            for kpi in kpi_records:
                try:
                    config = db.query(TeacherPayrollConfig).filter(
                        TeacherPayrollConfig.teacher_id == kpi.staff_id
                    ).first()
                    if not config:
                        errors.append(f"Giáo viên {kpi.staff_id} thiếu config lương")
                        continue

                    salary = db.query(Salary).filter(
                        Salary.teacher_id == kpi.staff_id,
                        Salary.period == period
                    ).first()

                    base_calc = config.base_salary if config.contract_type == ContractType.FULL_TIME else 0

                    # Guard: check if bonus from this KPI period was already paid
                    # in a different month's salary
                    already_paid = db.query(Salary).filter(
                        Salary.teacher_id == kpi.staff_id,
                        Salary.bonus_from_kpi_period_id == kpi_period.id,
                        Salary.kpi_bonus_calc > 0,
                        Salary.period != period,  # different month
                    ).first()

                    kpi_bonus = Decimal("0") if already_paid else (kpi.bonus_amount or Decimal("0"))
                    
                    if not salary:
                        salary = Salary(
                            teacher_id=kpi.staff_id,
                            period=period,
                            contract_type=config.contract_type,
                            lesson_count=int(kpi.teaching_hours or 0),
                            base_salary_calc=base_calc,
                            kpi_bonus_calc=kpi_bonus,
                            fixed_allowance=config.fixed_allowance,
                            net_salary=base_calc + kpi_bonus + config.fixed_allowance,
                            status=SalaryStatus.DRAFT,
                            bonus_from_kpi_period_id=kpi_period.id if kpi_bonus > 0 else None,
                        )
                        db.add(salary)
                    elif salary.status == SalaryStatus.DRAFT:
                        salary.contract_type = config.contract_type
                        salary.lesson_count = int(kpi.teaching_hours or 0)
                        salary.base_salary_calc = base_calc
                        salary.kpi_bonus_calc = kpi_bonus
                        salary.fixed_allowance = config.fixed_allowance
                        salary.bonus_from_kpi_period_id = kpi_period.id if kpi_bonus > 0 else salary.bonus_from_kpi_period_id
                        
                        salary.net_salary = base_calc + kpi_bonus + config.fixed_allowance + salary.total_adjustments
                    
                    processed += 1
                except Exception as e:
                    errors.append(f"Lỗi tính lương GV {kpi.staff_id}: {str(e)}")

            run.status = JobStatus.COMPLETED
            run.total_processed = processed
            run.finished_at = datetime.utcnow()
            if errors:
                run.error_log = "\n".join(errors)
            
            db.commit()

        except Exception as e:
            run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
            if run:
                run.status = JobStatus.FAILED
                run.error_log = str(e)
                run.finished_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()

salary_service = SalaryService()
teacher_payroll_config_service = TeacherPayrollConfigService()
payroll_run_service = PayrollRunService()
