from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.models.audit_log import AuditAction, AuditLogResponse
from sqlalchemy.orm import Session
from app.dependencies import CommonQueryParams, get_current_admin_user
from app.core.database import get_db
from app.schemas.base_schema import PaginationResponse
from app.services.audit_log_service import audit_service
from uuid import UUID
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])

@router.get("", response_model=PaginationResponse[AuditLogResponse])
async def get_audit_logs(
    # Pagination
    params: CommonQueryParams = Depends(),
    
    # Filters
    user_id: Optional[UUID] = Query(None, description="Lọc theo ID người thực hiện"),
    action: Optional[AuditAction] = Query(None, description="Lọc theo hành động (LOGIN, CREATE,...)"),
    table_name: Optional[str] = Query(None, description="Lọc theo tên bảng (users, classes...)"),
    record_id: Optional[UUID] = Query(None, description="Lọc theo ID bản ghi bị tác động"),
    success: Optional[bool] = Query(None, description="Lọc trạng thái thành công/thất bại"),
    search: Optional[str] = Query(None, description="Tìm kiếm trong table_name, error, user_agent"),

    # Dependencies
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Lấy danh sách nhật ký hệ thống (Audit Logs) có phân trang và lọc.
    Chỉ dành cho Admin.
    """

    result = audit_service.list_audit_logs(
        db=db,
        page=params.page,
        limit=params.limit,
        user_id=user_id,
        action=action,
        table_name=table_name,
        record_id=record_id,
        success=success,
        search=search
    )
    
    return result