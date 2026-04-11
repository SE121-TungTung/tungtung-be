"""
Invoice Schemas
Dựa trên model Invoice (app/models/finance.py) và note trong router invoice.
"""
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from app.models.finance import InvoiceStatus


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class InvoiceCreate(BaseModel):
    """POST /invoices – tạo hóa đơn cho enrollment."""
    enrollment_id: UUID = Field(..., description="ID đăng ký lớp học")
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0, description="Giảm giá (voucher, chính sách)")
    due_date: Optional[datetime] = Field(None, description="Hạn thanh toán")
    notes: Optional[str] = Field(None, description="Ghi chú hóa đơn")
    extra_metadata: Optional[dict] = Field(default=None, description="Breakdown giảm giá, v.v.")


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class InvoiceResponse(BaseModel):
    """Thông tin đầy đủ của hóa đơn – dùng cho cả list lẫn detail."""
    id: UUID
    student_id: UUID
    enrollment_id: UUID

    original_amount: Decimal = Field(..., description="Học phí gốc của khóa")
    discount_amount: Decimal = Field(..., description="Giảm giá")
    final_amount: Decimal = Field(..., description="= original - discount")

    status: InvoiceStatus
    due_date: Optional[datetime] = None
    notes: Optional[str] = None
    extra_metadata: Optional[dict] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
