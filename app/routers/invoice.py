"""
Invoice Router
POST   /api/v1/invoices          - Tạo hóa đơn (Office Admin+)
GET    /api/v1/invoices          - Admin xem danh sách tất cả hóa đơn
GET    /api/v1/invoices/me       - Học viên xem danh sách hóa đơn của mình
GET    /api/v1/invoices/{id}     - Xem chi tiết hóa đơn

NOTE: /me phải đặt TRƯỚC /{invoice_id} để FastAPI không nhầm "me" thành UUID.
"""
from fastapi import APIRouter, Depends, Query, Path, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import math

from app.core.database import get_db
from app.dependencies import get_current_user, require_role, require_any_role
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.models.user import User, UserRole

from app.schemas.finance.invoice import (
    InvoiceCreate,
    InvoiceResponse,
)

from app.services.finance.invoice_service import invoice_service

router = APIRouter(prefix="/invoices", tags=["Invoices"])

# Shorthand role dependencies
OfficeAdminUp = Depends(require_any_role(
    UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN
))


# ---------------------------------------------------------------------------
# POST /invoices
# Tạo hóa đơn: tính original_amount từ khóa học, áp giảm giá, xác định final_amount.
# Phân quyền: Office Admin, Center Admin, System Admin đều có thể tạo.
# ---------------------------------------------------------------------------
@router.post("", response_model=ApiResponse[InvoiceResponse])
async def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = OfficeAdminUp,
):
    result = invoice_service.create_invoice(db=db, payload=payload, created_by_id=current_user.id)
    return ApiResponse(success=True, data=result, message="Tạo hóa đơn thành công")


# ---------------------------------------------------------------------------
# GET /invoices  — Admin xem tất cả hóa đơn (phân trang)
# Phân quyền: Office Admin+ (cần quản lý/xem tất cả hóa đơn)
# ---------------------------------------------------------------------------
@router.get("", response_model=PaginationResponse[InvoiceResponse])
async def list_all_invoices(
    status: Optional[str] = Query(None, description="Lọc theo trạng thái (PENDING, PAID, CANCELLED, OVERDUE)"),
    student_id: Optional[UUID] = Query(None, description="Lọc theo học viên"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = OfficeAdminUp,
):
    items, total = invoice_service.list_all_invoices(
        db=db, status=status, student_id=student_id, page=page, limit=limit
    )
    meta = PaginationMetadata(
        page=page, limit=limit, total=total,
        total_pages=math.ceil(total / limit) if limit else 0
    )
    return PaginationResponse(success=True, data=items, meta=meta, message="Thành công")


# ---------------------------------------------------------------------------
# GET /invoices/me  — PHẢI đặt trước /{invoice_id}
# Học viên tự xem danh sách hóa đơn của mình (phân trang).
# Phân quyền: Mọi user đăng nhập (student xem của mình).
# ---------------------------------------------------------------------------
@router.get("/me", response_model=PaginationResponse[InvoiceResponse])
async def get_my_invoices(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = invoice_service.list_my_invoices(
        db=db, student_id=current_user.id, page=page, limit=limit
    )
    meta = PaginationMetadata(
        page=page, limit=limit, total=total,
        total_pages=math.ceil(total / limit) if limit else 0
    )
    return PaginationResponse(success=True, data=items, meta=meta, message="Thành công")


# ---------------------------------------------------------------------------
# GET /invoices/{invoice_id}
# Xem chi tiết hóa đơn. Student chỉ xem được của mình; Admin xem được tất cả.
# Phân quyền: Mọi user đăng nhập + service-level check (403 nếu student xem của người khác).
# ---------------------------------------------------------------------------
@router.get("/{invoice_id}", response_model=ApiResponse[InvoiceResponse])
async def get_invoice_detail(
    invoice_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = invoice_service.get_invoice_detail(
        db=db, invoice_id=invoice_id, current_user=current_user
    )
    return ApiResponse(success=True, data=result, message="Thành công")