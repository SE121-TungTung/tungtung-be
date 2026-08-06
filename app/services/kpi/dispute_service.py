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

        # Trigger notification to all active admins
        try:
            from app.services.notification_service import notification_service
            from app.schemas.notification import NotificationCreate
            from app.models.notification import NotificationType, NotificationPriority
            from app.models.user import User, UserRole, UserStatus

            teacher = db.query(User).filter(User.id == teacher_id).first()
            teacher_name = teacher.full_name if teacher else "Giáo viên"

            admins = db.query(User).filter(
                User.role.in_([UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN]),
                User.status == UserStatus.ACTIVE
            ).all()

            for admin in admins:
                noti_info = NotificationCreate(
                    user_id=admin.id,
                    title="Khiếu nại KPI mới cần xử lý",
                    content=f"Giáo viên {teacher_name} đã gửi một khiếu nại KPI mới với lý do: {payload.reason}",
                    notification_type=NotificationType.SYSTEM_ALERT,
                    priority=NotificationPriority.HIGH,
                    action_url="/admin/kpi/disputes",
                    channels=["in_app"]
                )
                notification_service.send_notification_sync(db, noti_info)
        except Exception as e:
            # Safe catch to avoid blocking the API response
            print(f"Failed to send dispute creation notification: {e}")

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

        if payload.status == DisputeStatus.RESOLVED and dispute.kpi_record_id:
            record = db.query(KPIRecord).filter(KPIRecord.id == dispute.kpi_record_id).first()
            if record:
                record.approval_status = ApprovalStatus.DRAFT

        db.commit()
        db.refresh(dispute)

        # Trigger notification to teacher
        try:
            from app.services.notification_service import notification_service
            from app.schemas.notification import NotificationCreate
            from app.models.notification import NotificationType, NotificationPriority

            status_str = "chấp nhận" if payload.status == DisputeStatus.RESOLVED else "từ chối"
            title = f"Khiếu nại KPI đã được giải quyết ({status_str.upper()})"
            content = f"Khiếu nại KPI của bạn đã được {status_str}. Phản hồi từ Admin: {payload.resolution_note}"
            action_url = "/teacher/kpi"

            noti_info = NotificationCreate(
                user_id=dispute.teacher_id,
                title=title,
                content=content,
                notification_type=NotificationType.SYSTEM_ALERT,
                priority=NotificationPriority.HIGH,
                action_url=action_url,
                channels=["in_app"]
            )
            notification_service.send_notification_sync(db, noti_info)
        except Exception as e:
            # Safe catch to avoid blocking the API response
            print(f"Failed to send dispute resolution notification: {e}")

        return dispute

    def list_disputes(
        self, db: Session, status: DisputeStatus = None, teacher_id: UUID = None, page: int = 1, limit: int = 20
    ) -> tuple:
        from app.models.user import User
        from app.models.kpi import KPIPeriod, KPIRecord

        query = (
            db.query(KpiDispute, User, KPIPeriod)
            .join(User, User.id == KpiDispute.teacher_id)
            .outerjoin(KPIRecord, KPIRecord.id == KpiDispute.kpi_record_id)
            .outerjoin(KPIPeriod, KPIPeriod.id == KPIRecord.period_id)
        )
        if status:
            query = query.filter(KpiDispute.status == status)
        if teacher_id:
            query = query.filter(KpiDispute.teacher_id == teacher_id)

        total = query.count()
        rows = (
            query.order_by(KpiDispute.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        items = []
        for row in rows:
            dispute = row[0]
            user = row[1]
            period = row[2]
            items.append({
                "id": dispute.id,
                "kpi_record_id": dispute.kpi_record_id,
                "teacher_id": dispute.teacher_id,
                "reason": dispute.reason,
                "status": dispute.status,
                "resolved_by": dispute.resolved_by,
                "resolution_note": dispute.resolution_note,
                "created_at": dispute.created_at,
                "resolved_at": dispute.resolved_at,
                "teacher_name": f"{user.first_name} {user.last_name}" if user else None,
                "period_name": period.name if period else None,
            })
        return items, total


kpi_dispute_service = KpiDisputeService()
