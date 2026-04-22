"""
KPI Dashboard Service — Summary, ranking, alerts, historical trends.
"""

from sqlalchemy.orm import Session
from sqlalchemy import func, case, desc
from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException
from decimal import Decimal
import logging

from app.models.kpi import (
    KPIRecord, KPIPeriod, KPIMetricResult, KPITemplateMetric,
    TeacherPayrollConfig, ApprovalStatus, ContractType, MetricUnit,
)
from app.models.user import User

logger = logging.getLogger(__name__)


class KPIDashboardService:

    def get_dashboard(self, db: Session, period_id: UUID) -> dict:
        """
        Dashboard summary for a period:
        - Staff counts, approval stats
        - Average score, total bonus
        - Top performers, alerts
        """
        period = db.query(KPIPeriod).filter(KPIPeriod.id == period_id).first()
        if not period:
            raise HTTPException(status_code=404, detail="Không tìm thấy kỳ KPI")

        records = db.query(KPIRecord).filter(KPIRecord.period_id == period_id).all()

        # Count by contract type
        teacher_count = 0
        ta_count = 0
        for r in records:
            config = db.query(TeacherPayrollConfig).filter(
                TeacherPayrollConfig.teacher_id == r.staff_id
            ).first()
            if config:
                if config.contract_type == ContractType.FULL_TIME:
                    teacher_count += 1
                else:
                    ta_count += 1
            else:
                teacher_count += 1  # Default

        # Approval stats
        draft_count = sum(1 for r in records if r.approval_status == ApprovalStatus.DRAFT)
        submitted_count = sum(1 for r in records if r.approval_status == ApprovalStatus.SUBMITTED)
        approved_count = sum(1 for r in records if r.approval_status == ApprovalStatus.APPROVED)
        rejected_count = sum(1 for r in records if r.approval_status == ApprovalStatus.REJECTED)

        # Score stats (only for records that have been calculated)
        scored_records = [r for r in records if r.total_score is not None]
        avg_score = None
        total_bonus = None
        if scored_records:
            avg_score = float(sum(float(r.total_score) for r in scored_records) / len(scored_records))
            total_bonus = float(sum(float(r.bonus_amount or 0) for r in scored_records))

        # Top 5 performers
        top_records = sorted(
            [r for r in scored_records],
            key=lambda x: float(x.total_score or 0),
            reverse=True,
        )[:5]

        top_performers = []
        for r in top_records:
            user = db.query(User).filter(User.id == r.staff_id).first()
            top_performers.append({
                "staff_id": str(r.staff_id),
                "staff_name": f"{user.first_name} {user.last_name}" if user else "N/A",
                "total_score": float(r.total_score),
                "bonus_amount": float(r.bonus_amount or 0),
            })

        # Alerts: records with A1 = 0 (below minimum threshold)
        alerts = []
        for r in records:
            if r.total_score is None:
                continue
            for mr in r.metric_results:
                metric = db.query(KPITemplateMetric).filter(
                    KPITemplateMetric.id == mr.metric_id
                ).first()
                if metric and metric.metric_code == "A1" and mr.converted_score is not None:
                    if float(mr.converted_score) == 0 and mr.actual_value is not None:
                        user = db.query(User).filter(User.id == r.staff_id).first()
                        alerts.append({
                            "type": "low_a1",
                            "staff_name": f"{user.first_name} {user.last_name}" if user else "N/A",
                            "message": f"A1 = 0 điểm (thực tế: {float(mr.actual_value):.1%})",
                            "record_id": str(r.id),
                        })

        return {
            "period_id": period_id,
            "period_name": period.name,
            "total_staff": len(records),
            "total_teachers": teacher_count,
            "total_ta": ta_count,
            "approved_count": approved_count,
            "submitted_count": submitted_count,
            "draft_count": draft_count,
            "rejected_count": rejected_count,
            "avg_score": round(avg_score, 4) if avg_score is not None else None,
            "total_bonus_amount": round(total_bonus, 2) if total_bonus is not None else None,
            "top_performers": top_performers,
            "alerts": alerts,
        }

    def get_ranking(
        self,
        db: Session,
        period_id: UUID,
        contract_type: Optional[str] = None,
    ) -> List[dict]:
        """
        Ranking table for a period, sorted by total_score desc.
        Optionally filter by contract_type (FULL_TIME, PART_TIME, NATIVE).
        """
        query = (
            db.query(KPIRecord, User, TeacherPayrollConfig)
            .join(User, User.id == KPIRecord.staff_id)
            .outerjoin(
                TeacherPayrollConfig,
                TeacherPayrollConfig.teacher_id == KPIRecord.staff_id,
            )
            .filter(
                KPIRecord.period_id == period_id,
                KPIRecord.total_score.isnot(None),
            )
        )

        if contract_type:
            query = query.filter(TeacherPayrollConfig.contract_type == contract_type)

        rows = query.order_by(desc(KPIRecord.total_score)).all()

        ranking = []
        for idx, row in enumerate(rows, 1):
            record, user, config = row
            ranking.append({
                "rank": idx,
                "staff_id": record.staff_id,
                "staff_name": f"{user.first_name} {user.last_name}",
                "contract_type": config.contract_type if config else None,
                "total_score": float(record.total_score),
                "bonus_amount": float(record.bonus_amount or 0),
                "approval_status": record.approval_status,
            })

        return ranking

    def get_staff_history(self, db: Session, staff_id: UUID) -> List[dict]:
        """Get KPI history across multiple periods for a staff member."""
        records = (
            db.query(KPIRecord, KPIPeriod)
            .join(KPIPeriod, KPIPeriod.id == KPIRecord.period_id)
            .filter(KPIRecord.staff_id == staff_id)
            .order_by(KPIPeriod.start_date.desc())
            .all()
        )

        history = []
        for record, period in records:
            history.append({
                "period_id": period.id,
                "period_name": period.name,
                "total_score": float(record.total_score) if record.total_score is not None else None,
                "bonus_amount": float(record.bonus_amount) if record.bonus_amount is not None else None,
                "approval_status": record.approval_status,
            })

        return history


kpi_dashboard_service = KPIDashboardService()
