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
    WalletTransaction, TransactionType, WalletRefType, WalletTxStatus,
)
from app.models.user import User, UserRole
from app.models.academic import ClassEnrollment, PaymentStatus as AcademicPaymentStatus
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

        # 3. Handle Internal Wallet Payment directly or regular gateway
        if payload.gateway == PaymentGateway.INTERNAL_WALLET:
            # Lock the user record to deduct balance safely
            student = db.query(User).filter(User.id == student_id).with_for_update().first()
            if not student:
                raise HTTPException(status_code=404, detail="Không tìm thấy thông tin tài khoản")

            if student.wallet_balance < payload.amount:
                raise HTTPException(
                    status_code=400,
                    detail="Số dư ví không đủ. Vui lòng nạp thêm tiền để tiếp tục."
                )

            # Deduct balance
            student.wallet_balance -= payload.amount

            # Create Wallet transaction
            tx = WalletTransaction(
                user_id=student_id,
                type=TransactionType.DEBIT,
                amount=payload.amount,
                balance_after=student.wallet_balance,
                reference_type=WalletRefType.TUITION,
                reference_id=invoice.id,
                status=WalletTxStatus.APPROVED,
                created_by=student_id,
                note=f"Thanh toán học phí cho hóa đơn {invoice.id.hex[:8].upper()}"
            )
            db.add(tx)

            # Create Payment record as SUCCESS
            payment = Payment(
                invoice_id=invoice.id,
                student_id=student_id,
                amount=payload.amount,
                gateway=payload.gateway,
                status=PaymentStatus.SUCCESS,
                idempotency_key=idempotency_key,
                paid_at=datetime.now(timezone.utc),
            )
            db.add(payment)
            db.flush()

            # Mark Invoice and Enrollment as Paid
            invoice.status = InvoiceStatus.PAID
            enrollment = db.query(ClassEnrollment).filter(
                ClassEnrollment.id == invoice.enrollment_id
            ).first()
            if enrollment:
                enrollment.payment_status = AcademicPaymentStatus.PAID
                enrollment.fee_paid = invoice.final_amount

            db.commit()
            db.refresh(payment)

            resp = self._to_response(payment)
            resp.payment_url = ""
            return resp

        # 3. Tạo Payment (VNPay/Momo/Cash/Bank Transfer)
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
                
                # Cập nhật Enrollment → PAID và lưu số tiền đã trả
                enrollment = db.query(ClassEnrollment).filter(
                    ClassEnrollment.id == invoice.enrollment_id
                ).first()
                if enrollment:
                    enrollment.payment_status = AcademicPaymentStatus.PAID
                    enrollment.fee_paid = invoice.final_amount
                    
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

        # Ensure the PDF file physically exists in media/receipts so the static server can serve it
        import os
        receipt_dir = os.path.join("media", "receipts")
        os.makedirs(receipt_dir, exist_ok=True)
        receipt_path = os.path.join(receipt_dir, f"{payment.id}.pdf")
        
        if not os.path.exists(receipt_path):
            paid_at_str = payment.paid_at.strftime('%Y-%m-%d %H:%M:%S') if payment.paid_at else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            stream_content = f"BT\n/F1 16 Tf\n70 700 Td\n(TungTung English Center - BIEN LAI THANH TOAN) Tj\n/F1 12 Tf\n0 -40 Td\n(Ma hoa don / Payment ID: {payment.id}) Tj\n0 -20 Td\n(So tien / Amount: {payment.amount:,.0f} VND) Tj\n0 -20 Td\n(Ngay thanh toan / Date: {paid_at_str}) Tj\n0 -30 Td\n(Cam on quy hoc vien da lua chon TungTung English Center!) Tj\nET".encode('utf-8')
            
            stream_len = len(stream_content)
            pdf_bytes = bytearray()
            pdf_bytes.extend(b"%PDF-1.4\n")
            
            # Object 1: Catalog
            obj1_pos = len(pdf_bytes)
            pdf_bytes.extend(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
            
            # Object 2: Pages
            obj2_pos = len(pdf_bytes)
            pdf_bytes.extend(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
            
            # Object 3: Page
            obj3_pos = len(pdf_bytes)
            pdf_bytes.extend(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>\nendobj\n")
            
            # Object 4: Font
            obj4_pos = len(pdf_bytes)
            pdf_bytes.extend(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
            
            # Object 5: Contents (Stream)
            obj5_pos = len(pdf_bytes)
            pdf_bytes.extend(f"5 0 obj\n<< /Length {stream_len} >>\nstream\n".encode('utf-8'))
            pdf_bytes.extend(stream_content)
            pdf_bytes.extend(b"\nendstream\nendobj\n")
            
            # Xref
            xref_pos = len(pdf_bytes)
            pdf_bytes.extend(b"xref\n0 6\n0000000000 65535 f \n")
            pdf_bytes.extend(f"{obj1_pos:010d} 00000 n \n".encode('utf-8'))
            pdf_bytes.extend(f"{obj2_pos:010d} 00000 n \n".encode('utf-8'))
            pdf_bytes.extend(f"{obj3_pos:010d} 00000 n \n".encode('utf-8'))
            pdf_bytes.extend(f"{obj4_pos:010d} 00000 n \n".encode('utf-8'))
            pdf_bytes.extend(f"{obj5_pos:010d} 00000 n \n".encode('utf-8'))
            
            # Trailer
            pdf_bytes.extend(b"trailer\n<< /Size 6 /Root 1 0 R >>\n")
            pdf_bytes.extend(f"startxref\n{xref_pos}\n%%EOF\n".encode('utf-8'))

            with open(receipt_path, "wb") as f:
                f.write(pdf_bytes)

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
