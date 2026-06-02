"""
KPI Support Calculator Service — Tool to compute A1/A2 rates from class exam data.
"""

from sqlalchemy.orm import Session
from uuid import UUID
from fastapi import HTTPException
import logging

from app.models.kpi import (
    SupportCalcEntry, KPIRecord, KPIMetricResult, KPITemplateMetric,
    ApprovalStatus, DataSource,
)
from app.schemas.kpi import SupportCalcRequest

logger = logging.getLogger(__name__)


class SupportCalcService:

    def calculate_rates(self, payload: SupportCalcRequest) -> dict:
        """
        Pure calculation — no database side effects.

        Output:
          rate_above_avg  = (above_avg_count + above_high_count) / class_size → A1
          rate_above_high = above_high_count / class_size                     → A2
        """
        class_size = payload.class_size
        above_avg = payload.above_avg_count
        above_high = payload.above_high_count

        rate_above_avg = (above_avg + above_high) / class_size
        rate_above_high = above_high / class_size

        return {
            "rate_above_avg": round(rate_above_avg, 4),
            "rate_above_high": round(rate_above_high, 4),
            "breakdown": {
                "total_students": class_size,
                "above_avg_only": above_avg,
                "above_high": above_high,
                "below_avg": class_size - above_avg - above_high,
            },
        }

    def save_and_apply(
        self, db: Session, record_id: UUID, payload: SupportCalcRequest
    ) -> dict:
        """
        Save calculator entry to DB and auto-apply results to A1/A2 metrics.
        """
        record = db.query(KPIRecord).filter(KPIRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi KPI")

        if record.approval_status == ApprovalStatus.APPROVED:
            raise HTTPException(
                status_code=400,
                detail="Không thể chỉnh sửa KPI đã được duyệt"
            )

        # Calculate rates
        rates = self.calculate_rates(payload)

        # Save entry
        entry = SupportCalcEntry(
            kpi_record_id=record_id,
            class_name=payload.class_name,
            class_size=payload.class_size,
            max_score=payload.max_score,
            avg_threshold=payload.avg_threshold,
            above_avg_count=payload.above_avg_count,
            high_threshold=payload.high_threshold,
            above_high_count=payload.above_high_count,
            rate_above_avg=rates["rate_above_avg"],
            rate_above_high=rates["rate_above_high"],
        )
        db.add(entry)
        db.flush()

        # Apply to A1 and A2 metric results
        results = (
            db.query(KPIMetricResult)
            .join(KPITemplateMetric, KPITemplateMetric.id == KPIMetricResult.metric_id)
            .filter(KPIMetricResult.kpi_record_id == record_id)
            .all()
        )

        for result in results:
            metric = db.query(KPITemplateMetric).filter(
                KPITemplateMetric.id == result.metric_id
            ).first()
            if not metric:
                continue

            if metric.metric_code == "A1":
                result.actual_value = rates["rate_above_avg"]
                result.data_source = DataSource.CALCULATED
                result.support_calc_id = entry.id
            elif metric.metric_code == "A2":
                result.actual_value = rates["rate_above_high"]
                result.data_source = DataSource.CALCULATED
                result.support_calc_id = entry.id

        db.commit()

        # Auto-recalculate after applying
        from app.services.kpi.calculation_service import kpi_calculation_service
        kpi_calculation_service.calculate_record(db, record_id)

        return {
            "entry_id": entry.id,
            **rates,
        }

    def get_calc_entries(self, db: Session, record_id: UUID) -> list:
        """Get all support calculator entries for a record."""
        return (
            db.query(SupportCalcEntry)
            .filter(SupportCalcEntry.kpi_record_id == record_id)
            .order_by(SupportCalcEntry.created_at.desc())
            .all()
        )


support_calc_service = SupportCalcService()
