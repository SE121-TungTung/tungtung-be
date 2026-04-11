"""
Refund Service
Business logic cho Refund module.

Doc reference (2.4.1 – Công thức hoàn tiền):
  - Bỏ học TRƯỚC ngày học đầu tiên: Hoàn 100%
  - Bỏ giữa khóa: Hoàn = (Buổi còn lại / Tổng buổi) × Học phí
  - Deadline xử lý: 3 ngày làm việc

LƯU Ý: Router note chỉ có công thức (remaining/total)*fee.
Doc bổ sung thêm trường hợp 100% nếu chưa bắt đầu.
→ Ưu tiên doc: nếu sessions_attended == 0 → hoàn 100%.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from uuid import UUID
from decimal import Decimal
from datetime import datetime, timezone
from fastapi import HTTPException

from app.models.finance import (
    Invoice, InvoiceStatus,
    Payment, PaymentStatus,
    Refund, RefundStatus,
)
from app.models.academic import ClassEnrollment, Class, EnrollmentStatus
from app.models.session_attendance import ClassSession, AttendanceRecord, SessionStatus
from app.models.user import User, UserRole
from app.schemas.finance.refund import (
    RefundCreate,
    RefundResponse,
    RefundStatusUpdate,
    RefundCalculationResponse,
)


class RefundService:

    def calculate_refund(
        self, db: Session, enrollment_id: UUID, current_user: User
    ) -> RefundCalculationResponse:
        """
        Tính trước số tiền hoàn (chỉ đọc).
        Doc: 100% nếu chưa học buổi nào, còn lại = (remaining/total)*fee
        """
        enrollment, class_obj = self._get_enrollment_with_class(db, enrollment_id)

        # Quyền: student chỉ xem của mình
        if (
            current_user.role == UserRole.STUDENT
            and enrollment.student_id != current_user.id
        ):
            raise HTTPException(status_code=403, detail="Bạn không có quyền xem thông tin hoàn tiền này")

        sessions_total = self._count_total_sessions(db, class_obj.id)
        sessions_attended = self._count_attended_sessions(db, class_obj.id, enrollment.student_id)
        sessions_remaining = sessions_total - sessions_attended

        # Lấy học phí đã thanh toán
        original_fee = self._get_paid_fee(db, enrollment_id)

        # Tính tiền hoàn (ưu tiên doc: 100% nếu chưa học)
        if sessions_attended == 0:
            refundable_amount = original_fee
        else:
            refundable_amount = (
                Decimal(str(sessions_remaining)) / Decimal(str(sessions_total)) * original_fee
                if sessions_total > 0
                else Decimal("0")
            )
        # Làm tròn 2 chữ số
        refundable_amount = refundable_amount.quantize(Decimal("0.01"))

        return RefundCalculationResponse(
            enrollment_id=enrollment_id,
            student_id=enrollment.student_id,
            sessions_total=sessions_total,
            sessions_attended=sessions_attended,
            sessions_remaining=sessions_remaining,
            original_fee=original_fee,
            refundable_amount=refundable_amount,
        )

    def create_refund(
        self, db: Session, payload: RefundCreate, requested_by: UUID
    ) -> RefundResponse:
        """
        Tạo yêu cầu hoàn tiền.
        - Validate không có Refund PENDING nào cho enrollment
        - Validate Payment gốc SUCCESS
        - Tính lại số tiền (100% nếu chưa học, otherwise pro-rata)
        - Persist Refund status=PENDING
        """
        enrollment, class_obj = self._get_enrollment_with_class(db, payload.enrollment_id)

        # Kiểm tra trùng
        existing = db.query(Refund).filter(
            Refund.enrollment_id == payload.enrollment_id,
            Refund.status == RefundStatus.PENDING,
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Đã có yêu cầu hoàn tiền đang chờ xử lý cho đăng ký này",
            )

        # Tìm payment SUCCESS cho enrollment
        payment = self._find_success_payment(db, payload.enrollment_id)

        sessions_total = self._count_total_sessions(db, class_obj.id)
        sessions_attended = self._count_attended_sessions(db, class_obj.id, enrollment.student_id)
        sessions_remaining = sessions_total - sessions_attended
        original_fee = Decimal(str(payment.amount))

        # Tính requested_amount — ưu tiên doc
        if sessions_attended == 0:
            requested_amount = original_fee
        else:
            requested_amount = (
                Decimal(str(sessions_remaining)) / Decimal(str(sessions_total)) * original_fee
                if sessions_total > 0
                else Decimal("0")
            )
        requested_amount = requested_amount.quantize(Decimal("0.01"))

        refund = Refund(
            enrollment_id=payload.enrollment_id,
            payment_id=payment.id,
            student_id=enrollment.student_id,
            sessions_total=sessions_total,
            sessions_attended=sessions_attended,
            sessions_remaining=sessions_remaining,
            original_fee=original_fee,
            requested_amount=requested_amount,
            status=RefundStatus.PENDING,
            reason=payload.reason,
            created_by=requested_by,
        )
        db.add(refund)
        db.commit()
        db.refresh(refund)

        return RefundResponse.model_validate(refund)

    def update_refund_status(
        self,
        db: Session,
        refund_id: UUID,
        payload: RefundStatusUpdate,
        admin_id: UUID,
    ) -> RefundResponse:
        """
        Phê duyệt (APPROVED) hoặc từ chối (REJECTED).
        - APPROVED: cập nhật approved_amount, Invoice status
        - REJECTED: lưu rejection_reason
        """
        refund = db.query(Refund).filter(Refund.id == refund_id).first()
        if not refund:
            raise HTTPException(status_code=404, detail="Không tìm thấy yêu cầu hoàn tiền")

        if refund.status != RefundStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail="Chỉ có thể xử lý yêu cầu đang ở trạng thái PENDING",
            )

        now = datetime.now(timezone.utc)

        if payload.status == RefundStatus.APPROVED:
            refund.status = RefundStatus.APPROVED
            refund.approved_amount = payload.approved_amount or refund.requested_amount
            refund.admin_note = payload.admin_note
            refund.reviewed_by = admin_id
            refund.reviewed_at = now

            # Cập nhật Invoice status
            invoice = (
                db.query(Invoice)
                .filter(Invoice.enrollment_id == refund.enrollment_id)
                .first()
            )
            if invoice:
                if refund.approved_amount >= invoice.final_amount:
                    invoice.status = InvoiceStatus.REFUNDED
                else:
                    invoice.status = InvoiceStatus.PARTIALLY_REFUNDED

        elif payload.status == RefundStatus.REJECTED:
            if not payload.rejection_reason:
                raise HTTPException(
                    status_code=400,
                    detail="Vui lòng cung cấp lý do từ chối",
                )
            refund.status = RefundStatus.REJECTED
            refund.rejection_reason = payload.rejection_reason
            refund.admin_note = payload.admin_note
            refund.reviewed_by = admin_id
            refund.reviewed_at = now
        else:
            raise HTTPException(status_code=400, detail="Status chỉ có thể là APPROVED hoặc REJECTED")

        db.commit()
        db.refresh(refund)
        return RefundResponse.model_validate(refund)

    # ----- private helpers -----

    def _get_enrollment_with_class(self, db: Session, enrollment_id: UUID):
        """Lấy enrollment + class, raise 404 nếu không tồn tại."""
        enrollment = db.query(ClassEnrollment).filter(
            ClassEnrollment.id == enrollment_id,
        ).first()
        if not enrollment:
            raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký khóa học")

        class_obj = db.query(Class).filter(Class.id == enrollment.class_id).first()
        if not class_obj:
            raise HTTPException(status_code=404, detail="Không tìm thấy lớp học liên quan")

        return enrollment, class_obj

    def _count_total_sessions(self, db: Session, class_id: UUID) -> int:
        """Tổng số buổi học (SCHEDULED + COMPLETED + IN_PROGRESS)."""
        return (
            db.query(func.count(ClassSession.id))
            .filter(
                ClassSession.class_id == class_id,
                ClassSession.status.in_([
                    SessionStatus.SCHEDULED,
                    SessionStatus.COMPLETED,
                    SessionStatus.IN_PROGRESS,
                ]),
            )
            .scalar() or 0
        )

    def _count_attended_sessions(self, db: Session, class_id: UUID, student_id: UUID) -> int:
        """Số buổi học viên đã tham dự (PRESENT hoặc LATE)."""
        from app.models.session_attendance import AttendanceStatus
        return (
            db.query(func.count(AttendanceRecord.id))
            .join(ClassSession, ClassSession.id == AttendanceRecord.session_id)
            .filter(
                ClassSession.class_id == class_id,
                AttendanceRecord.student_id == student_id,
                AttendanceRecord.status.in_([
                    AttendanceStatus.PRESENT,
                    AttendanceStatus.LATE,
                ]),
            )
            .scalar() or 0
        )

    def _get_paid_fee(self, db: Session, enrollment_id: UUID) -> Decimal:
        """Lấy số tiền đã thanh toán thành công gần nhất cho enrollment."""
        invoice = db.query(Invoice).filter(
            Invoice.enrollment_id == enrollment_id,
            Invoice.status.in_([InvoiceStatus.PAID.value, InvoiceStatus.PARTIALLY_REFUNDED.value]),
        ).first()
        if not invoice:
            raise HTTPException(status_code=400, detail="Không tìm thấy hóa đơn đã thanh toán cho đăng ký này")

        payment = db.query(Payment).filter(
            Payment.invoice_id == invoice.id,
            Payment.status == PaymentStatus.SUCCESS,
        ).order_by(Payment.paid_at.desc()).first()
        if not payment:
            raise HTTPException(status_code=400, detail="Không tìm thấy thanh toán thành công")

        return Decimal(str(payment.amount))

    def _find_success_payment(self, db: Session, enrollment_id: UUID) -> Payment:
        """Tìm Payment SUCCESS cho enrollment. Raise 400 nếu không có."""
        invoice = db.query(Invoice).filter(
            Invoice.enrollment_id == enrollment_id,
        ).first()
        if not invoice:
            raise HTTPException(status_code=400, detail="Không tìm thấy hóa đơn cho đăng ký này")

        payment = db.query(Payment).filter(
            Payment.invoice_id == invoice.id,
            Payment.status == PaymentStatus.SUCCESS,
        ).order_by(Payment.paid_at.desc()).first()
        if not payment:
            raise HTTPException(
                status_code=400,
                detail="Không tìm thấy thanh toán thành công để hoàn tiền",
            )
        return payment


refund_service = RefundService()
