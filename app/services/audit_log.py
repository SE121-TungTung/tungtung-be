from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from uuid import UUID

from app.models.audit_log import AuditLog, AuditAction
from sqlalchemy import or_

class AuditService:

    def log(
        self,
        db: Session,
        *,
        action: AuditAction,
        table_name: str,
        record_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[UUID] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """
        FAIL-SAFE audit logger
        Không được phép throw exception
        """
        try:
            log = AuditLog(
                user_id=user_id,
                action=action,
                table_name=table_name,
                record_id=record_id,
                old_values=old_values,
                new_values=new_values,
                ip_address=ip_address,
                user_agent=user_agent,
                session_id=session_id,
                success=success,
                error_message=error_message
            )
            db.add(log)
            db.flush()
        except Exception:
            pass

    def list_audit_logs(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[UUID] = None,
        action: Optional[AuditAction] = None,
        table_name: Optional[str] = None,
        record_id: Optional[UUID] = None,
        success: Optional[bool] = None,
        search: Optional[str] = None
    ):
        query = db.query(AuditLog)

        # ============================================================
        # Filters
        # ============================================================
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)

        if action:
            query = query.filter(AuditLog.action == action)

        if table_name:
            query = query.filter(AuditLog.table_name == table_name)

        if record_id:
            query = query.filter(AuditLog.record_id == record_id)

        if success is not None:
            query = query.filter(AuditLog.success == success)

        # ============================================================
        # Search (text-based, an toàn)
        # ============================================================
        if search:
            ilike = f"%{search}%"
            query = query.filter(
                or_(
                    AuditLog.table_name.ilike(ilike),
                    AuditLog.error_message.ilike(ilike),
                    AuditLog.user_agent.ilike(ilike)
                )
            )

        # ============================================================
        # Count trước pagination
        # ============================================================
        total = query.count()

        # ============================================================
        # Pagination + ordering
        # ============================================================
        items = (
            query
            .order_by(AuditLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        return {
            "total": total,
            "skip": skip,
            "limit": limit,
            "items": items
        }


audit_service = AuditService()
