"""
Refund Schemas
Dựa trên model Refund (app/models/finance.py) và note trong router refund.
Công thức: Tiền hoàn = (Buổi còn lại / Tổng buổi) × Học phí
"""
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from app.models.finance import RefundStatus


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class RefundCreate(BaseModel):
    """POST /refunds – tạo yêu cầu hoàn tiền."""
    enrollment_id: UUID = Field(..., description="ID đăng ký khóa học")
    reason: Optional[str] = Field(None, description="Lý do hoàn tiền")


class RefundStatusUpdate(BaseModel):
    """PATCH /refunds/{id}/status – phê duyệt hoặc từ chối."""
    status: RefundStatus = Field(..., description="APPROVED hoặc REJECTED")
    approved_amount: Optional[Decimal] = Field(None, ge=0, description="Số tiền admin duyệt (có thể khác requested)")
    rejection_reason: Optional[str] = Field(None, description="Lý do từ chối (bắt buộc nếu REJECTED)")
    admin_note: Optional[str] = Field(None, description="Ghi chú nội bộ của admin")


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class RefundCalculationResponse(BaseModel):
    """GET /refunds/calculate – preview số tiền hoàn trước khi tạo request."""
    enrollment_id: UUID
    student_id: UUID

    sessions_total: int = Field(..., description="Tổng số buổi khóa học")
    sessions_attended: int = Field(..., description="Số buổi đã học")
    sessions_remaining: int = Field(..., description="Số buổi còn lại")

    original_fee: Decimal = Field(..., description="Học phí đã thanh toán")
    refundable_amount: Decimal = Field(..., description="Số tiền có thể hoàn = (remaining/total) × fee")

    model_config = {"from_attributes": True}


class RefundResponse(BaseModel):
    """Thông tin đầy đủ yêu cầu hoàn tiền."""
    id: UUID
    enrollment_id: UUID
    payment_id: UUID
    student_id: UUID

    sessions_total: int
    sessions_attended: int
    sessions_remaining: int
    original_fee: Decimal

    requested_amount: Decimal
    approved_amount: Optional[Decimal] = None

    status: RefundStatus
    reason: Optional[str] = None
    rejection_reason: Optional[str] = None
    admin_note: Optional[str] = None

    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
