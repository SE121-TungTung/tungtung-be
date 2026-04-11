"""
Payment Schemas
Dựa trên model Payment (app/models/finance.py) và note trong router payment.
"""
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from app.models.finance import PaymentGateway, PaymentStatus


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class PaymentCreate(BaseModel):
    """POST /payments – khởi tạo thanh toán cho invoice."""
    invoice_id: UUID = Field(..., description="ID hóa đơn cần thanh toán")
    amount: Decimal = Field(..., gt=0, description="Số tiền thanh toán (phải == invoice.final_amount)")
    gateway: PaymentGateway = Field(..., description="Cổng thanh toán")


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class PaymentResponse(BaseModel):
    """Thông tin thanh toán – dùng cho list và detail."""
    id: UUID
    invoice_id: UUID
    student_id: UUID

    amount: Decimal
    gateway: PaymentGateway
    status: PaymentStatus

    idempotency_key: str
    gateway_transaction_id: Optional[str] = None
    gateway_response: Optional[dict] = None

    paid_at: Optional[datetime] = None
    receipt_url: Optional[str] = None
    payment_url: Optional[str] = Field(None, description="URL redirect tới cổng thanh toán")

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReceiptResponse(BaseModel):
    """GET /payments/{id}/receipt – link tải biên lai PDF."""
    payment_id: UUID
    receipt_url: str = Field(..., description="Presigned URL download PDF biên lai")
    expires_at: Optional[datetime] = Field(None, description="Thời điểm URL hết hạn")

    model_config = {"from_attributes": True}
