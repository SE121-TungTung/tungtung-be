"""
Finance Repository
Chứa toàn bộ raw DB queries cho Invoice, Payment, Refund, ReportExportJob.
"""
from __future__ import annotations

from typing import Optional, List, Tuple
from uuid import UUID

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.finance import (
    Invoice, InvoiceStatus,
    Payment, PaymentStatus,
    Refund, RefundStatus,
    ReportExportJob,
)

class InvoiceRepository:

    def create(self, db: Session, **kwargs) -> Invoice:
        invoice = Invoice(**kwargs)
        db.add(invoice)
        db.flush()
        return invoice

    def get_by_id(self, db: Session, invoice_id: UUID) -> Optional[Invoice]:
        return db.query(Invoice).filter(
            Invoice.id == invoice_id,
            Invoice.deleted_at.is_(None)
        ).first()

    def get_by_id_or_raise(self, db: Session, invoice_id: UUID) -> Invoice:
        invoice = self.get_by_id(db, invoice_id)
        if not invoice:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice không tồn tại")
        return invoice

    def list_by_student(
        self,
        db: Session,
        student_id: UUID,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[Invoice], int]:
        query = db.query(Invoice).filter(
            Invoice.student_id == student_id,
            Invoice.deleted_at.is_(None)
        )
        total = query.count()
        items = query.order_by(Invoice.created_at.desc()) \
                     .offset((page - 1) * limit) \
                     .limit(limit) \
                     .all()
        return items, total

    def update_status(self, db: Session, invoice: Invoice, status: InvoiceStatus) -> Invoice:
        invoice.status = status
        db.flush()
        return invoice

class PaymentRepository:

    def create(self, db: Session, **kwargs) -> Payment:
        payment = Payment(**kwargs)
        db.add(payment)
        db.flush()
        return payment

    def get_by_id(self, db: Session, payment_id: UUID) -> Optional[Payment]:
        return db.query(Payment).filter(
            Payment.id == payment_id,
            Payment.deleted_at.is_(None)
        ).first()

    def get_by_id_or_raise(self, db: Session, payment_id: UUID) -> Payment:
        payment = self.get_by_id(db, payment_id)
        if not payment:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment không tồn tại")
        return payment

    def get_by_idempotency_key(self, db: Session, key: str) -> Optional[Payment]:
        """Dùng để tránh double-charge: nếu key đã tồn tại → trả về payment cũ."""
        return db.query(Payment).filter(Payment.idempotency_key == key).first()

    def list_with_filters(
        self,
        db: Session,
        student_id: Optional[UUID] = None,
        status: Optional[PaymentStatus] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[Payment], int]:
        query = db.query(Payment).filter(Payment.deleted_at.is_(None))
        if student_id:
            query = query.filter(Payment.student_id == student_id)
        if status:
            query = query.filter(Payment.status == status)
        total = query.count()
        items = query.order_by(Payment.created_at.desc()) \
                     .offset((page - 1) * limit) \
                     .limit(limit) \
                     .all()
        return items, total

    def update(self, db: Session, payment: Payment, **kwargs) -> Payment:
        for key, value in kwargs.items():
            setattr(payment, key, value)
        db.flush()
        return payment

class RefundRepository:

    def create(self, db: Session, **kwargs) -> Refund:
        refund = Refund(**kwargs)
        db.add(refund)
        db.flush()
        return refund

    def get_by_id(self, db: Session, refund_id: UUID) -> Optional[Refund]:
        return db.query(Refund).filter(
            Refund.id == refund_id,
            Refund.deleted_at.is_(None)
        ).first()

    def get_by_id_or_raise(self, db: Session, refund_id: UUID) -> Refund:
        refund = self.get_by_id(db, refund_id)
        if not refund:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refund không tồn tại")
        return refund

    def get_by_enrollment(self, db: Session, enrollment_id: UUID) -> Optional[Refund]:
        """Lấy refund đang pending của enrollment (tránh tạo trùng)."""
        return db.query(Refund).filter(
            Refund.enrollment_id == enrollment_id,
            Refund.status == RefundStatus.PENDING.value,
            Refund.deleted_at.is_(None)
        ).first()

    def update_status(
        self,
        db: Session,
        refund: Refund,
        status: RefundStatus,
        **extra_fields,
    ) -> Refund:
        refund.status = status
        for key, value in extra_fields.items():
            setattr(refund, key, value)
        db.flush()
        return refund


class ReportExportJobRepository:

    def create(self, db: Session, **kwargs) -> ReportExportJob:
        job = ReportExportJob(**kwargs)
        db.add(job)
        db.flush()
        return job

    def get_by_id(self, db: Session, job_id: UUID) -> Optional[ReportExportJob]:
        return db.query(ReportExportJob).filter(
            ReportExportJob.id == job_id,
            ReportExportJob.deleted_at.is_(None)
        ).first()

    def update(self, db: Session, job: ReportExportJob, **kwargs) -> ReportExportJob:
        for key, value in kwargs.items():
            setattr(job, key, value)
        db.flush()
        return job

invoice_repository = InvoiceRepository()
payment_repository = PaymentRepository()
refund_repository = RefundRepository()
report_export_job_repository = ReportExportJobRepository()