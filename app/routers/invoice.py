"""
Invoice Router
POST   /api/v1/invoices          - Tạo hóa đơn
GET    /api/v1/invoices/me       - Học viên xem danh sách hóa đơn của mình
GET    /api/v1/invoices/{id}     - Xem chi tiết hóa đơn

NOTE: /me phải đặt TRƯỚC /{invoice_id} để FastAPI không nhầm "me" thành UUID.
"""
from fastapi import APIRouter, Depends, Query, Path, Body
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
import math

from app.core.database import get_db
from app.dependencies import get_current_user, require_role
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.models.user import User, UserRole

from app.schemas.finance.invoice import (
    InvoiceCreate,
    InvoiceResponse,
)

from app.services.finance.invoice_service import invoice_service

router = APIRouter(prefix="/invoices", tags=["Invoices"])


# ---------------------------------------------------------------------------
# POST /invoices
# Tạo hóa đơn: tính original_amount từ khóa học, áp giảm giá, xác định final_amount.
# Thường được gọi nội bộ sau khi enrollment thành công, hoặc bởi office_admin.
# ---------------------------------------------------------------------------
# invoice_service cần implement:
#   - invoice_service.create_invoice(db, payload, created_by_id) -> InvoiceResponse
#       + Validate enrollment_id tồn tại và chưa có invoice PENDING/PAID
#       + Tính original_amount từ course fee tại thời điểm đăng ký
#       + Áp discount nếu có (voucher, chính sách, chuyển lớp cùng cấp)
#       + Persist Invoice với status=PENDING
# ---------------------------------------------------------------------------
@router.post("", response_model=ApiResponse[InvoiceResponse])
async def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OFFICE_ADMIN)),
):
    result = invoice_service.create_invoice(db=db, payload=payload, created_by_id=current_user.id)
    return ApiResponse(success=True, data=result, message="Tạo hóa đơn thành công")


# ---------------------------------------------------------------------------
# GET /invoices/me  — PHẢI đặt trước /{invoice_id}
# Học viên tự xem danh sách hóa đơn của mình (phân trang).
# ---------------------------------------------------------------------------
# invoice_service cần implement:
#   - invoice_service.list_my_invoices(db, student_id, page, limit)
#       -> Tuple[List[InvoiceResponse], int]
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
# ---------------------------------------------------------------------------
# invoice_service cần implement:
#   - invoice_service.get_invoice_detail(db, invoice_id, current_user) -> InvoiceResponse
#       + Raise 404 nếu không tồn tại
#       + Raise 403 nếu student cố xem hóa đơn của người khác
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