from sqlalchemy import Column, String, Enum, Numeric, Text, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.models.base import BaseModel
import enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class InvoiceStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentGateway(enum.Enum):
    VNPAY = "vnpay"
    MOMO = "momo"
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"


class PaymentStatus(enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RefundStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"


class ReportType(enum.Enum):
    REVENUE = "revenue"
    EXPENSES = "expenses"
    PROFIT = "profit"
    DEBTS = "debts"


class ExportJobStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Invoice
# Được tạo khi học viên đăng ký lớp (enrollment).
# Lưu giá gốc, giảm giá, giá cuối để audit.
# ---------------------------------------------------------------------------

class Invoice(BaseModel):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_student_id", "student_id"),
        Index("ix_invoices_enrollment_id", "enrollment_id"),
        Index("ix_invoices_status", "status"),
    )

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    enrollment_id = Column(UUID(as_uuid=True), nullable=False)  # FK enrollments.id

    # Pricing breakdown
    original_amount = Column(Numeric(12, 2), nullable=False)   # Học phí gốc của khóa
    discount_amount = Column(Numeric(12, 2), nullable=False, default=0)  # Giảm giá (voucher, chính sách)
    final_amount = Column(Numeric(12, 2), nullable=False)       # = original - discount

    status = Column(
        Enum(InvoiceStatus, values_callable=lambda obj: [e.value for e in obj],
             native_enum=False, name="invoice_status"),
        default=InvoiceStatus.PENDING, nullable=False
    )

    due_date = Column(TIMESTAMP(timezone=True))
    notes = Column(Text)
    extra_metadata = Column("metadata", JSONB, default={})  # Lưu breakdown giảm giá, v.v.


# ---------------------------------------------------------------------------
# Payment
# Mỗi lần thanh toán cho một Invoice. Yêu cầu Idempotency-Key để tránh
# double-charge khi retry.
# ---------------------------------------------------------------------------

class Payment(BaseModel):
    __tablename__ = "payments"
    __table_args__ = (
        Index("uq_payments_idempotency_key", "idempotency_key", unique=True),
        Index("ix_payments_invoice_id", "invoice_id"),
        Index("ix_payments_student_id", "student_id"),
        Index("ix_payments_status", "status"),
    )

    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="RESTRICT"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    amount = Column(Numeric(12, 2), nullable=False)

    gateway = Column(
        Enum(PaymentGateway, values_callable=lambda obj: [e.value for e in obj],
             native_enum=False, name="payment_gateway"),
        nullable=False
    )
    status = Column(
        Enum(PaymentStatus, values_callable=lambda obj: [e.value for e in obj],
             native_enum=False, name="payment_status"),
        default=PaymentStatus.PENDING, nullable=False
    )

    # Idempotency: client gửi key duy nhất mỗi request để tránh trùng lặp
    idempotency_key = Column(String(128), nullable=False)

    # Dữ liệu từ cổng thanh toán
    gateway_transaction_id = Column(String(255), index=True)
    gateway_response = Column(JSONB)        # Raw response từ VNPay / MoMo
    gateway_webhook_payload = Column(JSONB) # Raw webhook payload

    paid_at = Column(TIMESTAMP(timezone=True))
    receipt_url = Column(Text)              # Link PDF biên lai (S3 / GCS)


# ---------------------------------------------------------------------------
# Refund
# Yêu cầu hoàn tiền khi học viên bỏ học giữa chừng.
# Công thức: Tiền hoàn = (Buổi còn lại / Tổng buổi) × Học phí
# ---------------------------------------------------------------------------

class Refund(BaseModel):
    __tablename__ = "refunds"
    __table_args__ = (
        Index("ix_refunds_enrollment_id", "enrollment_id"),
        Index("ix_refunds_student_id", "student_id"),
        Index("ix_refunds_status", "status"),
    )

    enrollment_id = Column(UUID(as_uuid=True), nullable=False)  # FK enrollments.id
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    # Tính toán hoàn tiền
    sessions_total = Column(Numeric(6, 0), nullable=False)      # Tổng số buổi khóa học
    sessions_attended = Column(Numeric(6, 0), nullable=False)   # Số buổi đã học
    sessions_remaining = Column(Numeric(6, 0), nullable=False)  # Buổi còn lại
    original_fee = Column(Numeric(12, 2), nullable=False)       # Học phí gốc tại thời điểm tính

    requested_amount = Column(Numeric(12, 2), nullable=False)   # Số tiền học viên yêu cầu / hệ thống tính
    approved_amount = Column(Numeric(12, 2))                    # Số tiền admin duyệt (có thể điều chỉnh)

    status = Column(
        Enum(RefundStatus, values_callable=lambda obj: [e.value for e in obj],
             native_enum=False, name="refund_status"),
        default=RefundStatus.PENDING, nullable=False
    )

    reason = Column(Text)                   # Lý do hoàn tiền
    rejection_reason = Column(Text)         # Lý do từ chối (nếu bị reject)
    admin_note = Column(Text)

    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = Column(TIMESTAMP(timezone=True))
    processed_at = Column(TIMESTAMP(timezone=True))  # Tiền đã trả lại thực tế


# ---------------------------------------------------------------------------
# ReportExportJob
# Bất đồng bộ: client POST để tạo job, server xử lý nền và cập nhật
# status + file_url khi xong. Client polling hoặc nhận webhook.
# ---------------------------------------------------------------------------

class ReportExportJob(BaseModel):
    __tablename__ = "report_export_jobs"
    __table_args__ = (
        Index("ix_export_jobs_created_by", "created_by"),
        Index("ix_export_jobs_status", "status"),
    )

    report_type = Column(
        Enum(ReportType, values_callable=lambda obj: [e.value for e in obj],
             native_enum=False, name="report_type"),
        nullable=False
    )
    status = Column(
        Enum(ExportJobStatus, values_callable=lambda obj: [e.value for e in obj],
             native_enum=False, name="export_job_status"),
        default=ExportJobStatus.PENDING, nullable=False
    )

    filters = Column(JSONB, default={})     # date_from, date_to, group_by, cost_type, etc.
    file_url = Column(Text)                 # Link download khi completed
    error_message = Column(Text)            # Chi tiết lỗi nếu failed

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    completed_at = Column(TIMESTAMP(timezone=True))