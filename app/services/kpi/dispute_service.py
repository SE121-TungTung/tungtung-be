from sqlalchemy.orm import Session
from uuid import UUID
from fastapi import HTTPException
from datetime import datetime
from typing import List

from app.models.kpi import KpiDispute, TeacherMonthlyKpi, DisputeStatus
from app.schemas.kpi import KpiDisputeCreate, KpiDisputeResolveRequest

class KpiDisputeService:
    def __init__(self, db: Session):
        self.db = db

    def create_dispute(self, teacher_id: UUID, payload: KpiDisputeCreate) -> KpiDispute:
        kpi_record = self.db.query(TeacherMonthlyKpi).filter(
            TeacherMonthlyKpi.id == payload.kpi_id,
            TeacherMonthlyKpi.teacher_id == teacher_id
        ).first()

        if not kpi_record:
            raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu KPI")

        # Nghiệp vụ: Chỉ chấp nhận xử lý dispute khi bảng KPI đã chốt và không quá deadline 48h
        # Wait, the logic in previous file says:
        # if not kpi_record.finalized_at:
        #     raise HTTPException(status_code=403, detail="KPI chưa được chốt, không thể khiếu nại")
        
        # We will keep the previous logic
        if not kpi_record.finalized_at:
            raise HTTPException(status_code=403, detail="KPI chưa được chốt, không thể khiếu nại")

        # Let's check status if it existed (in case some changes)
        if hasattr(kpi_record, "status") and getattr(kpi_record, "status") != "draft":
             raise HTTPException(status_code=403, detail="Bảng KPI đã chốt, không thể khiếu nại")

        # Deadline 48h (we must use timedelta from datetime)
        from datetime import timedelta
        if hasattr(kpi_record, "finalized_at") and kpi_record.finalized_at:
            if datetime.now() > kpi_record.finalized_at + timedelta(hours=48):
                raise HTTPException(status_code=403, detail="Hết thời hạn khiếu nại (48h sau khi chốt dữ liệu tạm tính)")

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

    def resolve_dispute(self, dispute_id: UUID, payload: KpiDisputeResolveRequest, admin_id: UUID) -> KpiDispute:
        dispute = self.db.query(KpiDispute).filter(KpiDispute.id == dispute_id).first()
        if not dispute:
            raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu khiếu nại")
        
        if dispute.status != DisputeStatus.PENDING:
            raise HTTPException(status_code=400, detail="Chỉ có thể giải quyết các khiếu nại đang ở trạng thái chờ (PENDING)")

        dispute.status = payload.status
        dispute.resolution_note = payload.resolution_note
        dispute.resolved_by = admin_id
        dispute.resolved_at = datetime.now()
        
        self.db.commit()
        self.db.refresh(dispute)
        return dispute
