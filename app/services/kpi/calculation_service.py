"""
KPI Calculation Engine — Lotus Scoring System

Scoring rules:
- RULE-01: actual < target_min → score = 0
- RULE-02: actual >= target_max → score = weight (full)
- RULE-03: Between min and max → linear interpolation
- RULE-04: For count/student units, min is effectively 0
"""

from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List
from uuid import UUID
import logging

from app.models.kpi import (
    KPIRecord, KPIMetricResult, KPITemplateMetric, KPITemplate,
    MetricUnit, ApprovalStatus, BonusType, ContractType,
    TeacherPayrollConfig,
)
from app.models.session_attendance import ClassSession, SessionStatus

logger = logging.getLogger(__name__)


class KPICalculationService:
    """Stateless calculation engine for KPI scoring."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_record(self, db: Session, record_id: UUID) -> KPIRecord:
        """Calculate all metric scores, total score, and bonus for a record."""
        record = db.query(KPIRecord).filter(KPIRecord.id == record_id).first()
        if not record:
            raise ValueError(f"KPI record {record_id} not found")

        if record.approval_status == ApprovalStatus.APPROVED:
            raise ValueError("Không thể tính lại KPI đã được duyệt")

        template = db.query(KPITemplate).filter(KPITemplate.id == record.template_id).first()
        if not template:
            raise ValueError(f"Template {record.template_id} not found")

        # Auto-calculate teaching hours from ClassSession
        teaching_hours = self._auto_calculate_teaching_hours(db, record)
        if record.teaching_hours is None:
            record.teaching_hours = teaching_hours

        # Calculate each metric
        total_score = Decimal("0")
        for result in record.metric_results:
            metric = result.metric
            if metric.is_group_header:
                continue

            if result.actual_value is not None:
                score = self.calculate_metric_score(
                    actual=Decimal(str(result.actual_value)),
                    target_min=Decimal(str(metric.target_min)) if metric.target_min is not None else Decimal("0"),
                    target_max=Decimal(str(metric.target_max)) if metric.target_max is not None else Decimal("1"),
                    weight=Decimal(str(metric.weight)) if metric.weight is not None else Decimal("0"),
                    unit=metric.unit,
                )
                result.converted_score = score
                total_score += score

                # Add note if below minimum
                if metric.unit in (MetricUnit.PERCENT, MetricUnit.SCORE):
                    if metric.target_min is not None and Decimal(str(result.actual_value)) < Decimal(str(metric.target_min)):
                        result.note = "Dưới ngưỡng tối thiểu"
                    else:
                        result.note = None
            else:
                result.converted_score = None

        # Round total score
        record.total_score = total_score.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        # Calculate bonus
        record.bonus_amount = self._calculate_bonus(
            total_score=record.total_score,
            template=template,
            teaching_hours=record.teaching_hours,
        )

        db.commit()
        db.refresh(record)
        return record

    def bulk_calculate_period(self, db: Session, period_id: UUID) -> dict:
        """Calculate all draft/submitted records in a period."""
        records = db.query(KPIRecord).filter(
            KPIRecord.period_id == period_id,
            KPIRecord.approval_status.in_([ApprovalStatus.DRAFT, ApprovalStatus.SUBMITTED]),
        ).all()

        processed = 0
        errors = []
        for record in records:
            try:
                self.calculate_record(db, record.id)
                processed += 1
            except Exception as e:
                errors.append(f"Record {record.id}: {str(e)}")
                logger.error(f"KPI calc error - {errors[-1]}")

        return {
            "total": len(records),
            "processed": processed,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Core Scoring Formula
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_metric_score(
        actual: Decimal,
        target_min: Decimal,
        target_max: Decimal,
        weight: Decimal,
        unit: Optional[MetricUnit],
    ) -> Decimal:
        """
        Calculate converted score for a single metric.

        For % and score units:
          - actual < min → 0
          - actual >= max → weight
          - else → weight × (actual - min) / (max - min)

        For count and student units:
          - actual <= 0 → 0
          - actual >= max → weight
          - else → weight × actual / max
        """
        if weight <= 0:
            return Decimal("0")

        if unit in (MetricUnit.PERCENT, MetricUnit.SCORE):
            if actual < target_min:
                return Decimal("0")
            elif actual >= target_max:
                return weight
            else:
                denominator = target_max - target_min
                if denominator <= 0:
                    return weight
                return (weight * (actual - target_min) / denominator).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )

        elif unit in (MetricUnit.COUNT, MetricUnit.STUDENT):
            if actual <= 0:
                return Decimal("0")
            elif actual >= target_max:
                return weight
            else:
                if target_max <= 0:
                    return weight
                return (weight * actual / target_max).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )

        # Fallback: treat as percentage-type
        if actual < target_min:
            return Decimal("0")
        elif actual >= target_max:
            return weight
        else:
            denominator = target_max - target_min
            if denominator <= 0:
                return weight
            return (weight * (actual - target_min) / denominator).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )

    # ------------------------------------------------------------------
    # Bonus Calculation
    # ------------------------------------------------------------------

    def _calculate_bonus(
        self,
        total_score: Decimal,
        template: KPITemplate,
        teaching_hours: Optional[Decimal],
    ) -> Decimal:
        """
        GV (FIXED_PER_PERIOD): bonus = max_bonus × total_score
        TA (PER_HOUR):         bonus = max_bonus_per_hour × teaching_hours × total_score
        """
        max_bonus = Decimal(str(template.max_bonus_amount))

        if template.bonus_type == BonusType.FIXED_PER_PERIOD:
            bonus = max_bonus * total_score
        elif template.bonus_type == BonusType.PER_HOUR:
            hours = Decimal(str(teaching_hours)) if teaching_hours else Decimal("0")
            bonus = max_bonus * hours * total_score
        else:
            bonus = Decimal("0")

        return bonus.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # ------------------------------------------------------------------
    # Auto-calculate teaching hours
    # ------------------------------------------------------------------

    def _auto_calculate_teaching_hours(
        self, db: Session, record: KPIRecord
    ) -> Decimal:
        """Count completed class sessions for this teacher in the period's date range."""
        from app.models.kpi import KPIPeriod

        period = db.query(KPIPeriod).filter(KPIPeriod.id == record.period_id).first()
        if not period:
            return Decimal("0")

        count = (
            db.query(ClassSession)
            .filter(
                ClassSession.teacher_id == record.staff_id,
                ClassSession.status == SessionStatus.COMPLETED,
                ClassSession.session_date >= period.start_date,
                ClassSession.session_date <= period.end_date,
            )
            .count()
        )
        # Each session = 1 teaching hour (default assumption)
        return Decimal(str(count))


kpi_calculation_service = KPICalculationService()
