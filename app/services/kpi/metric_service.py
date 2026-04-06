from sqlalchemy.orm import Session
from fastapi import HTTPException
from datetime import datetime

from app.models.kpi import KpiRawMetric
from app.schemas.kpi import KpiRawMetricSync

class KpiMetricService:
    def __init__(self, db: Session):
        self.db = db

    def sync_metrics(self, payload: KpiRawMetricSync) -> str:
        try:
            existing = self.db.query(KpiRawMetric).filter(
                KpiRawMetric.teacher_id == payload.teacher_id,
                KpiRawMetric.period == payload.period,
                KpiRawMetric.source_module == payload.source_module,
            ).first()

            if existing:
                existing.metric_data = payload.metric_data
                existing.synced_at = datetime.utcnow()
            else:
                new_metric = KpiRawMetric(
                    teacher_id=payload.teacher_id,
                    period=payload.period,
                    source_module=payload.source_module,
                    metric_data=payload.metric_data,
                )
                self.db.add(new_metric)
            
            self.db.commit()
            return "Đồng bộ dữ liệu thành công"
        except Exception as e:
            self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Lỗi khi đồng bộ metric: {str(e)}")
