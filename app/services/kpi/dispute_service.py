"""
KPI Dispute Service — Migrated to reference KPIRecord.
"""

from sqlalchemy.orm import Session
from uuid import UUID
from fastapi import HTTPException
from datetime import datetime, timedelta
from typing import List

from app.models.kpi import KpiDispute, KPIRecord, ApprovalStatus, DisputeStatus
from app.schemas.kpi import KpiDisputeCreate, KpiDisputeResolveRequest


class KpiDisputeService:

    def create_dispute(
        self, db: Session, teacher_id: UUID, payload: KpiDisputeCreate
    ) -> KpiDispute:
        # Find the KPI record
        record = db.query(KPIRecord).filter(
            KPIRecord.id == payload.kpi_record_id,
            KPIRecord.staff_id == teacher_id,
        ).first()

        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy dữ liệu KPI")

        # Only allow disputes on approved records
        if record.approval_status != ApprovalStatus.APPROVED:
            raise HTTPException(
                status_code=403,
                detail="Chỉ có thể khiếu nại KPI đã được duyệt"
            )

        # Deadline: 48h after approval
        if record.approved_at:
            if datetime.utcnow() > record.approved_at + timedelta(hours=48):
                raise HTTPException(
                    status_code=403,
                    detail="Hết thời hạn khiếu nại (48h sau khi duyệt)"
                )

        # Check for existing pending dispute
        existing = db.query(KpiDispute).filter(
            KpiDispute.kpi_record_id == payload.kpi_record_id,
            KpiDispute.teacher_id == teacher_id,
            KpiDispute.status == DisputeStatus.PENDING,
        ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="Đã có khiếu nại đang xử lý cho KPI này"
            )

        dispute = KpiDispute(
            kpi_record_id=payload.kpi_record_id,
            teacher_id=teacher_id,
            reason=payload.reason,
            status=DisputeStatus.PENDING,
        )
        db.add(dispute)
        db.commit()
        db.refresh(dispute)
        return dispute

    def resolve_dispute(
        self,
        db: Session,
        dispute_id: UUID,
        payload: KpiDisputeResolveRequest,
        admin_id: UUID,
    ) -> KpiDispute:
        dispute = db.query(KpiDispute).filter(KpiDispute.id == dispute_id).first()
        if not dispute:
            raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu khiếu nại")

        if dispute.status != DisputeStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail="Chỉ có thể giải quyết các khiếu nại đang ở trạng thái chờ (PENDING)"
            )

        dispute.status = payload.status
        dispute.resolution_note = payload.resolution_note
        dispute.resolved_by = admin_id
        dispute.resolved_at = datetime.utcnow()

        db.commit()
        db.refresh(dispute)
        return dispute

    def list_disputes(
        self, db: Session, status: DisputeStatus = None, page: int = 1, limit: int = 20
    ) -> tuple:
        query = db.query(KpiDispute)
        if status:
            query = query.filter(KpiDispute.status == status)

        total = query.count()
        disputes = (
            query.order_by(KpiDispute.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return disputes, total


kpi_dispute_service = KpiDisputeService()
