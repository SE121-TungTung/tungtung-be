"""
KPI Record Service — CRUD, metric input, approval workflow.
"""

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List, Optional, Tuple
from uuid import UUID
from fastapi import HTTPException
from datetime import datetime
import math
import logging

from app.models.kpi import (
    KPIRecord, KPIMetricResult, KPITemplateMetric, KPITemplate,
    KPIPeriod, KPIApprovalLog, TeacherPayrollConfig,
    ApprovalStatus, ApprovalAction, DataSource,
)
from app.models.user import User, UserRole
from app.schemas.kpi import (
    UpdateMetricsRequest, MetricActualValueInput,
    KPIRecordListItem, KPIRecordDetailResponse,
    MetricResultResponse, RejectRequest,
)
from app.services.kpi.calculation_service import kpi_calculation_service

logger = logging.getLogger(__name__)


class KPIRecordService:

    # ------------------------------------------------------------------
    # List & Detail
    # ------------------------------------------------------------------

    def list_records(
        self,
        db: Session,
        period_id: Optional[UUID] = None,
        staff_id: Optional[UUID] = None,
        status: Optional[ApprovalStatus] = None,
        contract_type: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[dict], int]:
        """List KPI records with filters."""
        query = (
            db.query(KPIRecord, User, KPIPeriod, TeacherPayrollConfig)
            .join(User, User.id == KPIRecord.staff_id)
            .join(KPIPeriod, KPIPeriod.id == KPIRecord.period_id)
            .outerjoin(
                TeacherPayrollConfig,
                TeacherPayrollConfig.teacher_id == KPIRecord.staff_id,
            )
        )

        if period_id:
            query = query.filter(KPIRecord.period_id == period_id)
        if staff_id:
            query = query.filter(KPIRecord.staff_id == staff_id)
        if status:
            query = query.filter(KPIRecord.approval_status == status)
        if contract_type:
            query = query.filter(TeacherPayrollConfig.contract_type == contract_type)

        total = query.count()
        rows = (
            query.order_by(User.first_name)
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        items = []
        for row in rows:
            record = row[0]
            user = row[1]
            period = row[2]
            config = row[3]
            items.append({
                "id": record.id,
                "staff_id": record.staff_id,
                "staff_name": f"{user.first_name} {user.last_name}",
                "staff_contract": config.contract_type if config else None,
                "period_id": record.period_id,
                "period_name": period.name,
                "total_score": float(record.total_score) if record.total_score is not None else None,
                "bonus_amount": float(record.bonus_amount) if record.bonus_amount is not None else None,
                "teaching_hours": float(record.teaching_hours) if record.teaching_hours is not None else None,
                "approval_status": record.approval_status,
                "submitted_at": record.submitted_at,
                "approved_at": record.approved_at,
            })

        return items, total

    def get_record_detail(self, db: Session, record_id: UUID) -> dict:
        """Get full record detail with metric breakdown."""
        record = (
            db.query(KPIRecord)
            .options(
                joinedload(KPIRecord.metric_results).joinedload(KPIMetricResult.metric),
                joinedload(KPIRecord.period),
                joinedload(KPIRecord.template),
            )
            .filter(KPIRecord.id == record_id)
            .first()
        )
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi KPI")

        user = db.query(User).filter(User.id == record.staff_id).first()
        config = db.query(TeacherPayrollConfig).filter(
            TeacherPayrollConfig.teacher_id == record.staff_id
        ).first()

        # Build metric list (sorted by template sort_order)
        # Include group headers from template
        template_metrics = (
            db.query(KPITemplateMetric)
            .filter(KPITemplateMetric.template_id == record.template_id)
            .order_by(KPITemplateMetric.sort_order)
            .all()
        )

        result_map = {r.metric_id: r for r in record.metric_results}

        metrics_response = []
        for tm in template_metrics:
            result = result_map.get(tm.id)

            if tm.is_group_header:
                # Calculate group score (sum of child metric scores)
                group_code = tm.metric_code  # e.g. 'A'
                group_score = sum(
                    float(r.converted_score)
                    for r in record.metric_results
                    if r.metric and r.metric.metric_code.startswith(group_code)
                       and not r.metric.is_group_header
                       and r.converted_score is not None
                )
                metrics_response.append({
                    "id": str(tm.id),
                    "metric_code": tm.metric_code,
                    "metric_name": tm.metric_name,
                    "is_group_header": True,
                    "unit": None,
                    "target_min": None,
                    "target_max": None,
                    "weight": None,
                    "group_weight": float(tm.group_weight) if tm.group_weight else None,
                    "actual_value": None,
                    "converted_score": round(group_score, 4),
                    "data_source": None,
                    "note": None,
                })
            elif result:
                metrics_response.append({
                    "id": str(result.id),
                    "metric_code": tm.metric_code,
                    "metric_name": tm.metric_name,
                    "is_group_header": False,
                    "unit": tm.unit,
                    "target_min": float(tm.target_min) if tm.target_min is not None else None,
                    "target_max": float(tm.target_max) if tm.target_max is not None else None,
                    "weight": float(tm.weight) if tm.weight is not None else None,
                    "group_weight": None,
                    "actual_value": float(result.actual_value) if result.actual_value is not None else None,
                    "converted_score": float(result.converted_score) if result.converted_score is not None else None,
                    "data_source": result.data_source,
                    "note": result.note,
                })

        return {
            "id": record.id,
            "staff_id": record.staff_id,
            "staff_name": f"{user.first_name} {user.last_name}" if user else None,
            "staff_contract": config.contract_type if config else None,
            "period": record.period,
            "template": record.template,
            "total_score": float(record.total_score) if record.total_score is not None else None,
            "bonus_amount": float(record.bonus_amount) if record.bonus_amount is not None else None,
            "teaching_hours": float(record.teaching_hours) if record.teaching_hours is not None else None,
            "approval_status": record.approval_status,
            "submitted_at": record.submitted_at,
            "approved_by": record.approved_by,
            "approved_at": record.approved_at,
            "rejection_note": record.rejection_note,
            "metrics": metrics_response,
        }

    def get_my_record(
        self, db: Session, user_id: UUID, period_id: UUID
    ) -> dict:
        """Get teacher/TA's own KPI record."""
        record = db.query(KPIRecord).filter(
            KPIRecord.staff_id == user_id,
            KPIRecord.period_id == period_id,
        ).first()
        if not record:
            raise HTTPException(
                status_code=404,
                detail="Không tìm thấy dữ liệu KPI của bạn trong kỳ này"
            )
        return self.get_record_detail(db, record.id)

    # ------------------------------------------------------------------
    # Metric Input
    # ------------------------------------------------------------------

    def update_metrics(
        self, db: Session, record_id: UUID, payload: UpdateMetricsRequest
    ) -> KPIRecord:
        """Update actual_value for metrics in a record."""
        record = db.query(KPIRecord).filter(KPIRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi KPI")

        if record.approval_status == ApprovalStatus.APPROVED:
            raise HTTPException(
                status_code=400,
                detail="Không thể chỉnh sửa KPI đã được duyệt"
            )

        # Build metric code → result mapping
        results = (
            db.query(KPIMetricResult)
            .join(KPITemplateMetric, KPITemplateMetric.id == KPIMetricResult.metric_id)
            .filter(KPIMetricResult.kpi_record_id == record_id)
            .all()
        )

        # Map metric_code → result
        code_to_result = {}
        for r in results:
            metric = db.query(KPITemplateMetric).filter(
                KPITemplateMetric.id == r.metric_id
            ).first()
            if metric:
                code_to_result[metric.metric_code] = r

        # Apply updates
        for m_input in payload.metrics:
            result = code_to_result.get(m_input.metric_code)
            if not result:
                raise HTTPException(
                    status_code=400,
                    detail=f"Không tìm thấy tiêu chí {m_input.metric_code}"
                )
            result.actual_value = m_input.actual_value
            result.data_source = DataSource.MANUAL

        # If record was rejected, move back to draft on edit
        if record.approval_status == ApprovalStatus.REJECTED:
            record.approval_status = ApprovalStatus.DRAFT
            record.rejection_note = None

        db.commit()

        # Auto-calculate after update
        return kpi_calculation_service.calculate_record(db, record_id)

    def update_teaching_hours(
        self, db: Session, record_id: UUID, teaching_hours: float
    ) -> KPIRecord:
        """Manually adjust teaching hours for a record."""
        record = db.query(KPIRecord).filter(KPIRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi KPI")

        if record.approval_status == ApprovalStatus.APPROVED:
            raise HTTPException(
                status_code=400,
                detail="Không thể chỉnh sửa KPI đã được duyệt"
            )

        record.teaching_hours = teaching_hours
        db.commit()

        # Recalculate bonus with new hours
        return kpi_calculation_service.calculate_record(db, record_id)

    # ------------------------------------------------------------------
    # Approval Workflow
    # ------------------------------------------------------------------

    def submit_record(self, db: Session, record_id: UUID, actor_id: UUID) -> KPIRecord:
        """Submit a record for approval."""
        record = db.query(KPIRecord).filter(KPIRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi KPI")

        if record.approval_status not in (ApprovalStatus.DRAFT, ApprovalStatus.REJECTED):
            raise HTTPException(
                status_code=400,
                detail=f"Chỉ có thể submit bản ghi ở trạng thái DRAFT hoặc REJECTED (hiện: {record.approval_status.value})"
            )

        # Ensure calculation is done
        kpi_calculation_service.calculate_record(db, record_id)

        record.approval_status = ApprovalStatus.SUBMITTED
        record.submitted_at = datetime.utcnow()
        record.rejection_note = None

        # Log
        log = KPIApprovalLog(
            kpi_record_id=record_id,
            action=ApprovalAction.SUBMIT,
            actor_id=actor_id,
            comment="Submitted for review",
        )
        db.add(log)
        db.commit()
        db.refresh(record)
        return record

    def approve_record(self, db: Session, record_id: UUID, admin_id: UUID) -> KPIRecord:
        """Approve a submitted record."""
        record = db.query(KPIRecord).filter(KPIRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi KPI")

        if record.approval_status != ApprovalStatus.SUBMITTED:
            raise HTTPException(
                status_code=400,
                detail="Chỉ có thể duyệt bản ghi đã submit"
            )

        record.approval_status = ApprovalStatus.APPROVED
        record.approved_by = admin_id
        record.approved_at = datetime.utcnow()

        log = KPIApprovalLog(
            kpi_record_id=record_id,
            action=ApprovalAction.APPROVE,
            actor_id=admin_id,
            comment="Approved",
        )
        db.add(log)
        db.commit()
        db.refresh(record)
        return record

    def reject_record(
        self, db: Session, record_id: UUID, admin_id: UUID, comment: str
    ) -> KPIRecord:
        """Reject a submitted record (comment required)."""
        record = db.query(KPIRecord).filter(KPIRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi KPI")

        if record.approval_status != ApprovalStatus.SUBMITTED:
            raise HTTPException(
                status_code=400,
                detail="Chỉ có thể từ chối bản ghi đã submit"
            )

        record.approval_status = ApprovalStatus.REJECTED
        record.rejection_note = comment

        log = KPIApprovalLog(
            kpi_record_id=record_id,
            action=ApprovalAction.REJECT,
            actor_id=admin_id,
            comment=comment,
        )
        db.add(log)
        db.commit()
        db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Approval Log
    # ------------------------------------------------------------------

    def get_approval_log(self, db: Session, record_id: UUID) -> List[KPIApprovalLog]:
        record = db.query(KPIRecord).filter(KPIRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi KPI")

        return (
            db.query(KPIApprovalLog)
            .filter(KPIApprovalLog.kpi_record_id == record_id)
            .order_by(KPIApprovalLog.created_at)
            .all()
        )


kpi_record_service = KPIRecordService()
