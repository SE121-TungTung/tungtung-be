"""
Payment Router
POST   /api/v1/payments                          - Thực hiện thanh toán (yêu cầu Idempotency-Key)
POST   /api/v1/payments/webhooks/{gateway}       - Nhận webhook từ VNPay / MoMo
GET    /api/v1/payments/{payment_id}/receipt     - Tải / lấy link PDF biên lai
GET    /api/v1/payments                          - Lịch sử thanh toán (filter + phân trang)

NOTE: Route tĩnh (/webhooks/{gateway}) phải đặt TRƯỚC route động (/{payment_id}/...).
"""
from fastapi import APIRouter, Depends, Query, Path, Header, Request
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
import math

from app.core.database import get_db
from app.dependencies import get_current_user, require_role
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.models.user import User, UserRole
from app.models.finance import PaymentGateway, PaymentStatus

from app.schemas.finance.payment import (
    PaymentCreate,
    PaymentResponse,
    ReceiptResponse,
)

from app.services.finance.payment_service import payment_service

router = APIRouter(prefix="/payments", tags=["Payments"])


# ---------------------------------------------------------------------------
# POST /payments
# Thực hiện thanh toán cho một Invoice.
# Header: Idempotency-Key (bắt buộc) để tránh double-charge khi client retry.
# ---------------------------------------------------------------------------
# payment_service cần implement:
#   - payment_service.process_payment(db, payload, idempotency_key, student_id)
#       -> PaymentResponse
#       + Kiểm tra idempotency_key đã tồn tại → trả về payment cũ (HTTP 200)
#       + Validate invoice tồn tại, status=PENDING, student khớp
#       + Validate amount == invoice.final_amount
#       + Tạo Payment với status=PENDING
#       + Gọi payment gateway (VNPay / MoMo) → nhận redirect_url hoặc QR
#       + Cập nhật gateway_transaction_id
#       + Trả về PaymentResponse kèm payment_url cho client redirect
# ---------------------------------------------------------------------------
@router.post("", response_model=ApiResponse[PaymentResponse])
async def process_payment(
    payload: PaymentCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = payment_service.process_payment(
        db=db,
        payload=payload,
        idempotency_key=idempotency_key,
        student_id=current_user.id,
    )
    return ApiResponse(success=True, data=result, message="Khởi tạo thanh toán thành công")


# ---------------------------------------------------------------------------
# POST /payments/webhooks/{gateway}
# Endpoint public (không auth) nhận callback từ cổng thanh toán.
# Phải đặt TRƯỚC /{payment_id}/receipt để tránh "webhooks" bị parse là UUID.
# ---------------------------------------------------------------------------
# payment_service cần implement:
#   - payment_service.handle_webhook(db, gateway, raw_body, headers)
#       -> dict  (trả về format mà gateway yêu cầu, VD: {"RspCode":"00"} cho VNPay)
#       + Verify chữ ký / HMAC từ gateway
#       + Lookup Payment theo gateway_transaction_id
#       + Cập nhật status (SUCCESS / FAILED) và gateway_response
#       + Nếu SUCCESS → cập nhật Invoice.status = PAID
#       + Trigger tạo receipt PDF bất đồng bộ (background task)
#       + Ghi log webhook để audit
# ---------------------------------------------------------------------------
@router.post("/webhooks/{gateway}")
async def payment_webhook(
    request: Request,
    gateway: PaymentGateway = Path(...),
    db: Session = Depends(get_db),
):
    raw_body = await request.body()
    result = payment_service.handle_webhook(
        db=db,
        gateway=gateway,
        raw_body=raw_body,
        headers=dict(request.headers),
    )
    return result


# ---------------------------------------------------------------------------
# GET /payments/{payment_id}/receipt
# Tải hoặc lấy presigned URL của PDF biên lai thanh toán.
# ---------------------------------------------------------------------------
# payment_service cần implement:
#   - payment_service.get_receipt(db, payment_id, current_user) -> ReceiptResponse
#       + Validate payment tồn tại, status=SUCCESS
#       + Authorization: student chỉ lấy được receipt của mình
#       + Nếu receipt_url đã có → trả về presigned URL (refresh nếu expired)
#       + Nếu chưa có → trigger tạo PDF (blocking hoặc async tùy SLA)
# ---------------------------------------------------------------------------
@router.get("/{payment_id}/receipt", response_model=ApiResponse[ReceiptResponse])
async def get_payment_receipt(
    payment_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = payment_service.get_receipt(
        db=db, payment_id=payment_id, current_user=current_user
    )
    return ApiResponse(success=True, data=result, message="Thành công")


# ---------------------------------------------------------------------------
# GET /payments?student_id={id}&status={status}
# Lấy lịch sử thanh toán. Admin có thể filter theo bất kỳ student;
# Student chỉ xem được của mình (service tự enforce).
# ---------------------------------------------------------------------------
# payment_service cần implement:
#   - payment_service.list_payments(db, student_id, status, page, limit, current_user)
#       -> Tuple[List[PaymentResponse], int]
#       + Student: bắt buộc filter student_id == current_user.id
#       + Admin: filter tự do
# ---------------------------------------------------------------------------
@router.get("", response_model=PaginationResponse[PaymentResponse])
async def list_payments(
    student_id: Optional[UUID] = Query(None),
    status: Optional[PaymentStatus] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items, total = payment_service.list_payments(
        db=db,
        student_id=student_id,
        status=status,
        page=page,
        limit=limit,
        current_user=current_user,
    )
    meta = PaginationMetadata(
        page=page, limit=limit, total=total,
        total_pages=math.ceil(total / limit) if limit else 0
    )
    return PaginationResponse(success=True, data=items, meta=meta, message="Thành công")