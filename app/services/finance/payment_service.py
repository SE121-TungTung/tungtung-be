"""
Payment Service
Business logic cho Payment module.

Doc reference (2.4.1):
- Hỗ trợ phương thức: Cash, Bank Transfer, E-wallet
- Phát hành biên lai/hóa đơn cho mỗi giao dịch
- Học viên đóng toàn bộ một lần khi enrollment (không chia thanh toán)
"""
from sqlalchemy.orm import Session
from typing import List, Tuple, Optional
from uuid import UUID
from datetime import datetime, timezone
from fastapi import HTTPException

from app.models.finance import (
    Invoice, InvoiceStatus,
    Payment, PaymentGateway, PaymentStatus,
)
from app.models.user import User, UserRole
from app.schemas.finance.payment import PaymentCreate, PaymentResponse, ReceiptResponse


class PaymentService:

    def process_payment(
        self,
        db: Session,
        payload: PaymentCreate,
        idempotency_key: str,
        student_id: UUID,
    ) -> PaymentResponse:
        """
        Thực hiện thanh toán cho một Invoice.
        - Kiểm tra idempotency_key → nếu trùng trả payment cũ
        - Validate invoice tồn tại, status=PENDING, student khớp
        - Validate amount == invoice.final_amount
        - Tạo Payment status=PENDING
        - Gọi gateway (stub) → nhận payment_url
        """
        # 1. Idempotency check
        existing = db.query(Payment).filter(
            Payment.idempotency_key == idempotency_key,
        ).first()
        if existing:
            return self._to_response(existing)

        # 2. Validate invoice
        invoice = db.query(Invoice).filter(
            Invoice.id == payload.invoice_id,
            Invoice.deleted_at.is_(None),
        ).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Không tìm thấy hóa đơn")

        if invoice.status != InvoiceStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Hóa đơn đang ở trạng thái {invoice.status.value}, không thể thanh toán",
            )

        if invoice.student_id != student_id:
            raise HTTPException(status_code=403, detail="Bạn không có quyền thanh toán hóa đơn này")

        if payload.amount != invoice.final_amount:
            raise HTTPException(
                status_code=400,
                detail=f"Số tiền thanh toán ({payload.amount}) không khớp với hóa đơn ({invoice.final_amount})",
            )

        # 3. Tạo Payment
        payment = Payment(
            invoice_id=invoice.id,
            student_id=student_id,
            amount=payload.amount,
            gateway=payload.gateway,
            status=PaymentStatus.PENDING,
            idempotency_key=idempotency_key,
        )
        db.add(payment)
        db.flush()

        # 4. Gọi payment gateway (stub — trả về URL giả)
        payment_url = self._initiate_gateway_payment(payment, payload.gateway)

        db.commit()
        db.refresh(payment)

        resp = self._to_response(payment)
        resp.payment_url = payment_url
        return resp

    def handle_webhook(
        self,
        db: Session,
        gateway: PaymentGateway,
        raw_body: bytes,
        headers: dict,
    ) -> dict:
        """
        Nhận callback từ cổng thanh toán.
        - Verify chữ ký / HMAC
        - Cập nhật status (SUCCESS / FAILED)
        - Nếu SUCCESS → Invoice.status = PAID
        """
        # 1. Parse và verify (gateway-specific, stub)
        parsed = self._parse_webhook(gateway, raw_body, headers)
        transaction_id = parsed.get("transaction_id")
        success = parsed.get("success", False)

        # 2. Lookup payment
        payment = db.query(Payment).filter(
            Payment.gateway_transaction_id == transaction_id,
        ).first()
        if not payment:
            return {"RspCode": "01", "Message": "Payment not found"}

        # 3. Cập nhật payment
        payment.gateway_webhook_payload = parsed
        if success:
            payment.status = PaymentStatus.SUCCESS
            payment.paid_at = datetime.now(timezone.utc)

            # Cập nhật Invoice → PAID
            invoice = db.query(Invoice).filter(Invoice.id == payment.invoice_id).first()
            if invoice:
                invoice.status = InvoiceStatus.PAID

        else:
            payment.status = PaymentStatus.FAILED

        db.commit()
        return {"RspCode": "00", "Message": "OK"}

    def get_receipt(
        self, db: Session, payment_id: UUID, current_user: User
    ) -> ReceiptResponse:
        """
        Lấy presigned URL của PDF biên lai.
        - Validate payment tồn tại, status=SUCCESS
        - Student chỉ lấy receipt của mình
        """
        payment = db.query(Payment).filter(Payment.id == payment_id).first()
        if not payment:
            raise HTTPException(status_code=404, detail="Không tìm thấy thanh toán")

        if payment.status != PaymentStatus.SUCCESS:
            raise HTTPException(status_code=400, detail="Chỉ có thể lấy biên lai cho thanh toán thành công")

        # Authorization
        if (
            current_user.role == UserRole.STUDENT
            and payment.student_id != current_user.id
        ):
            raise HTTPException(status_code=403, detail="Bạn không có quyền lấy biên lai này")

        # Nếu chưa có receipt → tạo placeholder (thực tế sẽ generate PDF + upload S3)
        if not payment.receipt_url:
            payment.receipt_url = f"/receipts/{payment.id}.pdf"
            db.commit()

        return ReceiptResponse(
            payment_id=payment.id,
            receipt_url=payment.receipt_url,
            expires_at=None,
        )

    def list_payments(
        self,
        db: Session,
        student_id: Optional[UUID],
        status: Optional[PaymentStatus],
        page: int,
        limit: int,
        current_user: User,
    ) -> Tuple[List[PaymentResponse], int]:
        """
        Lịch sử thanh toán (filter + phân trang).
        Student chỉ xem của mình; Admin xem tự do.
        """
        query = db.query(Payment)

        # Student bắt buộc chỉ xem của mình
        if current_user.role == UserRole.STUDENT:
            query = query.filter(Payment.student_id == current_user.id)
        elif student_id:
            query = query.filter(Payment.student_id == student_id)

        if status:
            query = query.filter(Payment.status == status)

        total = query.count()
        items = (
            query
            .order_by(Payment.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return [self._to_response(p) for p in items], total

    # ----- private helpers -----

    def _to_response(self, payment: Payment) -> PaymentResponse:
        return PaymentResponse.model_validate(payment)

    def _initiate_gateway_payment(self, payment: Payment, gateway: PaymentGateway) -> str:
        """
        Stub: gọi payment gateway thực tế (VNPay/MoMo/...).
        Trả về redirect URL cho client.
        Trong production sẽ tích hợp SDK của gateway tương ứng.
        """
        # Giả lập gateway_transaction_id
        import uuid as _uuid
        payment.gateway_transaction_id = str(_uuid.uuid4())

        if gateway == PaymentGateway.CASH:
            # Cash không cần redirect
            return ""
        # Stub URL
        return f"https://pay.example.com/checkout/{payment.gateway_transaction_id}"

    def _parse_webhook(self, gateway: PaymentGateway, raw_body: bytes, headers: dict) -> dict:
        """
        Stub: parse + verify webhook payload từ gateway.
        Trong production sẽ verify HMAC/signature theo từng gateway.
        """
        import json
        try:
            data = json.loads(raw_body)
        except Exception:
            data = {}
        return {
            "transaction_id": data.get("transaction_id", ""),
            "success": data.get("status") == "success",
            "raw": data,
        }


payment_service = PaymentService()
