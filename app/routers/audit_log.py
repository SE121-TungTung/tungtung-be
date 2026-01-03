from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.models.audit_log import AuditLogListResponse, AuditAction
from sqlalchemy.orm import Session
from app.dependencies import get_current_admin_user
from app.core.database import get_db
from app.services.audit_log import audit_service
from uuid import UUID
from app.models.user import User

router = APIRouter(prefix="/audit_logs", tags=["Audit Logs"])

@router.get("/", response_model=AuditLogListResponse)
async def get_audit_logs(
    # Pagination
    skip: int = Query(0, ge=0, description="Số lượng bản ghi bỏ qua"),
    limit: int = Query(20, ge=1, le=100, description="Số lượng bản ghi tối đa mỗi trang"),
    
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
        skip=skip,
        limit=limit,
        user_id=user_id,
        action=action,
        table_name=table_name,
        record_id=record_id,
        success=success,
        search=search
    )
    
    return result