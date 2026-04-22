"""
KPI Period Service — Period management and auto-record creation.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException
import logging

from app.models.kpi import (
    KPIPeriod, KPIRecord, KPIMetricResult, KPITemplate, KPITemplateMetric,
    ApprovalStatus, TeacherPayrollConfig, DataSource,
)
from app.models.user import User, UserRole
from app.schemas.kpi import KPIPeriodCreate

logger = logging.getLogger(__name__)


class KPIPeriodService:

    def list_periods(self, db: Session) -> List[KPIPeriod]:
        return db.query(KPIPeriod).order_by(KPIPeriod.start_date.desc()).all()

    def get_period(self, db: Session, period_id: UUID) -> KPIPeriod:
        period = db.query(KPIPeriod).filter(KPIPeriod.id == period_id).first()
        if not period:
            raise HTTPException(status_code=404, detail="Không tìm thấy kỳ KPI")
        return period

    def get_period_detail(self, db: Session, period_id: UUID) -> dict:
        """Get period with record count stats."""
        period = self.get_period(db, period_id)

        stats = db.query(
            func.count(KPIRecord.id).label("total"),
            func.count(KPIRecord.id).filter(
                KPIRecord.approval_status == ApprovalStatus.DRAFT
            ).label("draft"),
            func.count(KPIRecord.id).filter(
                KPIRecord.approval_status == ApprovalStatus.SUBMITTED
            ).label("submitted"),
            func.count(KPIRecord.id).filter(
                KPIRecord.approval_status == ApprovalStatus.APPROVED
            ).label("approved"),
            func.count(KPIRecord.id).filter(
                KPIRecord.approval_status == ApprovalStatus.REJECTED
            ).label("rejected"),
        ).filter(KPIRecord.period_id == period_id).one()

        return {
            "id": period.id,
            "name": period.name,
            "period_type": period.period_type,
            "start_date": period.start_date,
            "end_date": period.end_date,
            "is_active": period.is_active,
            "created_at": period.created_at,
            "total_records": stats.total,
            "draft_count": stats.draft,
            "submitted_count": stats.submitted,
            "approved_count": stats.approved,
            "rejected_count": stats.rejected,
        }

    def create_period(self, db: Session, payload: KPIPeriodCreate, created_by: UUID) -> dict:
        """
        Create a new KPI period and auto-generate KPIRecords for all active staff.
        Uses contract_type to determine which template to use:
        - FULL_TIME → teacher template
        - PART_TIME / NATIVE → TA template
        """
        period = KPIPeriod(
            name=payload.name,
            period_type=payload.period_type,
            start_date=payload.start_date,
            end_date=payload.end_date,
            is_active=True,
            created_by=created_by,
        )
        db.add(period)
        db.flush()

        # Get active templates (latest version, is_active)
        templates = db.query(KPITemplate).filter(KPITemplate.is_active == True).all()
        template_map = {}
        for t in templates:
            # Map contract_type → template
            key = t.contract_type.value
            if key not in template_map or t.version > template_map[key].version:
                template_map[key] = t

        # Get all staff (teachers) with payroll configs
        staff_configs = db.query(TeacherPayrollConfig).all()

        # Also check from User table for teachers without configs
        teachers = db.query(User).filter(
            User.role == UserRole.TEACHER,
            User.deleted_at.is_(None),
        ).all()

        records_created = 0
        skipped = []

        for teacher in teachers:
            config = None
            for sc in staff_configs:
                if sc.teacher_id == teacher.id:
                    config = sc
                    break

            contract_type_key = config.contract_type.value if config else "FULL_TIME"
            template = template_map.get(contract_type_key)

            if not template:
                skipped.append(f"Staff {teacher.id}: No template for {contract_type_key}")
                continue

            # Create KPI record
            record = KPIRecord(
                staff_id=teacher.id,
                period_id=period.id,
                template_id=template.id,
                approval_status=ApprovalStatus.DRAFT,
            )
            db.add(record)
            db.flush()

            # Create empty metric results from template
            for tm in template.metrics:
                if tm.is_group_header:
                    continue  # Skip group headers (A, B, C, D)

                result = KPIMetricResult(
                    kpi_record_id=record.id,
                    metric_id=tm.id,
                    data_source=DataSource.MANUAL,
                )
                db.add(result)

            records_created += 1

        db.commit()
        db.refresh(period)

        return {
            "period": period,
            "records_created": records_created,
            "skipped": skipped,
        }

    def close_period(self, db: Session, period_id: UUID) -> KPIPeriod:
        """Close a period — lock all approved records."""
        period = self.get_period(db, period_id)

        if not period.is_active:
            raise HTTPException(status_code=400, detail="Kỳ KPI đã đóng")

        period.is_active = False
        db.commit()
        db.refresh(period)
        return period


kpi_period_service = KPIPeriodService()
