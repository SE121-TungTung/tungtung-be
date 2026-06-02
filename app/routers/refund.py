"""
Refund Router
GET    /api/v1/refunds/calculate?enrollment_id={id} - Tính số tiền được hoàn
POST   /api/v1/refunds                              - Tạo yêu cầu hoàn tiền
PATCH  /api/v1/refunds/{id}/status                  - Phê duyệt / từ chối hoàn tiền

Công thức hoàn tiền (từ BRD 2.1.3):
  Tiền hoàn = (Số buổi còn lại / Tổng số buổi) × Học phí
  Thời gian xử lý: 3 ngày làm việc
"""
from fastapi import APIRouter, Depends, Query, Path, Body
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.dependencies import get_current_user, require_role
from app.schemas.base_schema import ApiResponse
from app.models.user import User, UserRole

from app.schemas.finance.refund import (
    RefundCalculationResponse,
    RefundCreate,
    RefundResponse,
    RefundStatusUpdate,
)

from app.services.finance.refund_service import refund_service

router = APIRouter(prefix="/refunds", tags=["Refunds"])


# ---------------------------------------------------------------------------
# GET /refunds/calculate?enrollment_id={id}
# Tính trước số tiền sẽ được hoàn dựa trên tiến độ khóa học.
# Chỉ đọc — không tạo bất kỳ bản ghi nào.
# Phải đặt TRƯỚC /{id}/status để tránh "calculate" bị parse là UUID.
# ---------------------------------------------------------------------------
# refund_service cần implement:
#   - refund_service.calculate_refund(db, enrollment_id, current_user)
#       -> RefundCalculationResponse
#       + Validate enrollment tồn tại và đang ACTIVE
#       + Lấy số buổi đã học (từ attendance records)
#       + Lấy tổng buổi của khóa học
#       + Lấy học phí đã thanh toán (Payment SUCCESS gần nhất của enrollment)
#       + Tính: refundable = (remaining / total) * fee
#       + Trả về breakdown để học viên / admin xem trước khi quyết định
# ---------------------------------------------------------------------------
@router.get("/calculate", response_model=ApiResponse[RefundCalculationResponse])
async def calculate_refund(
    enrollment_id: UUID = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = refund_service.calculate_refund(
        db=db, enrollment_id=enrollment_id, current_user=current_user
    )
    return ApiResponse(success=True, data=result, message="Thành công")


# ---------------------------------------------------------------------------
# POST /refunds
# Tạo yêu cầu hoàn tiền. Thường do office_admin thay mặt học viên tạo,
# hoặc do student tự tạo tùy policy.
# ---------------------------------------------------------------------------
# refund_service cần implement:
#   - refund_service.create_refund(db, payload, requested_by) -> RefundResponse
#       + Validate không có Refund PENDING nào đang tồn tại cho enrollment này
#       + Validate Payment gốc ở trạng thái SUCCESS
#       + Tính toán lại số tiền (gọi lại calculate logic)
#       + Persist Refund với status=PENDING
#       + Gửi notification đến Center Admin để duyệt
# ---------------------------------------------------------------------------
@router.post("", response_model=ApiResponse[RefundResponse])
async def create_refund(
    payload: RefundCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.OFFICE_ADMIN)),
):
    result = refund_service.create_refund(
        db=db, payload=payload, requested_by=current_user.id
    )
    return ApiResponse(success=True, data=result, message="Tạo yêu cầu hoàn tiền thành công")


# ---------------------------------------------------------------------------
# PATCH /refunds/{id}/status
# Phê duyệt (APPROVED) hoặc từ chối (REJECTED) yêu cầu hoàn tiền.
# Chỉ Center Admin có quyền.
# ---------------------------------------------------------------------------
# refund_service cần implement:
#   - refund_service.update_refund_status(db, refund_id, payload, admin_id)
#       -> RefundResponse
#       + Validate refund đang ở status PENDING (không thể thay đổi đã duyệt)
#       + Nếu APPROVED:
#           - Cập nhật approved_amount (có thể admin điều chỉnh khác requested)
#           - Cập nhật Invoice/Payment nếu cần
#           - Trigger hoàn tiền thực tế qua gateway (hoặc đánh dấu chờ xử lý thủ công)
#       + Nếu REJECTED:
#           - Lưu rejection_reason
#       + Gửi notification đến student
# ---------------------------------------------------------------------------
@router.patch("/{refund_id}/status", response_model=ApiResponse[RefundResponse])
async def update_refund_status(
    refund_id: UUID = Path(...),
    payload: RefundStatusUpdate = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CENTER_ADMIN)),
):
    result = refund_service.update_refund_status(
        db=db, refund_id=refund_id, payload=payload, admin_id=current_user.id
    )
    return ApiResponse(success=True, data=result, message="Cập nhật trạng thái hoàn tiền thành công")