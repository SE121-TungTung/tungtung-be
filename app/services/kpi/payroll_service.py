from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Tuple
from uuid import UUID
from fastapi import HTTPException, BackgroundTasks
from datetime import datetime
from decimal import Decimal

from app.models.kpi import Salary, SalaryStatus, SalaryAdjustment, AdjustmentType, TeacherPayrollConfig, PayrollRun, JobStatus, ContractType, TeacherMonthlyKpi
from app.models.user import User, UserRole
from app.schemas.kpi import SalaryAdjustmentCreate, TeacherPayrollConfigUpdate, PayrollRunCreate

class SalaryService:
    def __init__(self, db: Session):
        self.db = db

    def get_salary(self, salary_id: UUID, current_user: User) -> Salary:
        salary = self.db.query(Salary).filter(Salary.id == salary_id).first()
        if not salary:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiếu lương")

        if salary.teacher_id != current_user.id and current_user.role != UserRole.CENTER_ADMIN:
            raise HTTPException(status_code=403, detail="Không có quyền xem phiếu lương này")

        return salary

    def get_history(self, teacher_id: UUID, period: str | None, page: int, limit: int) -> Tuple[List[Salary], int]:
        query = self.db.query(Salary).filter(Salary.teacher_id == teacher_id)
        if period:
            query = query.filter(Salary.period == period)
            
        total = query.count()
        salaries = query.order_by(Salary.period.desc()).offset((page - 1) * limit).limit(limit).all()
        return salaries, total

    def get_all(self, period: str | None, page: int, limit: int) -> Tuple[List[Salary], int]:
        query = self.db.query(Salary)
        if period:
            query = query.filter(Salary.period == period)
            
        total = query.count()
        salaries = query.order_by(Salary.period.desc()).offset((page - 1) * limit).limit(limit).all()
        return salaries, total

    def approve(self, salary_id: UUID, admin_id: UUID) -> Salary:
        salary = self.db.query(Salary).filter(Salary.id == salary_id).first()
        if not salary:
            raise HTTPException(status_code=404, detail="Không tìm thấy phiếu lương")
            
        if salary.status != SalaryStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Chỉ có thể duyệt phiếu lương đang ở trạng thái DRAFT")

        salary.status = SalaryStatus.APPROVED
        salary.approved_by = admin_id
        salary.approved_at = datetime.now()
        
        self.db.commit()
        self.db.refresh(salary)
        return salary

    def add_adjustment(self, salary_id: UUID, payload: SalaryAdjustmentCreate, admin_id: UUID) -> SalaryAdjustment:
        salary = self.db.query(Salary).filter(Salary.id == salary_id).first()
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
        self.db.add(adjustment)
        self.db.commit()
        self.db.refresh(adjustment)
        return adjustment


class TeacherPayrollConfigService:
    def __init__(self, db: Session):
        self.db = db

    def update_config(self, teacher_id: UUID, payload: TeacherPayrollConfigUpdate) -> TeacherPayrollConfig:
        config = self.db.query(TeacherPayrollConfig).filter(TeacherPayrollConfig.teacher_id == teacher_id).first()
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
            self.db.add(config)
            
        self.db.commit()
        self.db.refresh(config)
        return config


class PayrollRunService:
    def __init__(self, db: Session):
        self.db = db

    def create_run(self, payload: PayrollRunCreate, bg_tasks: BackgroundTasks) -> PayrollRun:
        existing = self.db.query(PayrollRun).filter(PayrollRun.period == payload.period).first()
        if existing and existing.status in [JobStatus.PENDING, JobStatus.PROCESSING]:
            raise HTTPException(status_code=409, detail="Tiến trình tính lương đang chạy")
            
        if not existing:
            run = PayrollRun(period=payload.period, status=JobStatus.PENDING)
            self.db.add(run)
        else:
            run = existing
            run.status = JobStatus.PENDING
            run.error_log = None
            
        self.db.commit()
        self.db.refresh(run)

        bg_tasks.add_task(self._process_payroll, run.id, payload.period)
        return run

    def _process_payroll(self, run_id: UUID, period: str):
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            run = db.query(PayrollRun).filter(PayrollRun.id == run_id).first()
            if not run:
                return

            run.status = JobStatus.PROCESSING
            db.commit()

            kpi_records = db.query(TeacherMonthlyKpi).filter(TeacherMonthlyKpi.period == period).all()
            
            processed = 0
            errors = []
            
            for kpi in kpi_records:
                try:
                    config = db.query(TeacherPayrollConfig).filter(TeacherPayrollConfig.teacher_id == kpi.teacher_id).first()
                    if not config:
                        errors.append(f"Giáo viên {kpi.teacher_id} thiếu config lương")
                        continue

                    salary = db.query(Salary).filter(
                        Salary.teacher_id == kpi.teacher_id,
                        Salary.period == period
                    ).first()

                    base_calc = config.base_salary if config.contract_type == ContractType.FULL_TIME else 0
                    
                    if not salary:
                        salary = Salary(
                            teacher_id=kpi.teacher_id,
                            period=period,
                            contract_type=config.contract_type,
                            lesson_count=0,
                            base_salary_calc=base_calc,
                            kpi_bonus_calc=kpi.calculated_bonus,
                            fixed_allowance=config.fixed_allowance,
                            net_salary=base_calc + kpi.calculated_bonus + config.fixed_allowance,
                            status=SalaryStatus.DRAFT
                        )
                        db.add(salary)
                    elif salary.status == SalaryStatus.DRAFT:
                        salary.contract_type = config.contract_type
                        salary.base_salary_calc = base_calc
                        salary.kpi_bonus_calc = kpi.calculated_bonus
                        salary.fixed_allowance = config.fixed_allowance
                        
                        salary.net_salary = base_calc + kpi.calculated_bonus + config.fixed_allowance + salary.total_adjustments
                    
                    processed += 1
                except Exception as e:
                    errors.append(f"Lỗi tính lương GV {kpi.teacher_id}: {str(e)}")

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
