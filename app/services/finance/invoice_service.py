"""
Invoice Service
Business logic cho Invoice module.

Doc reference (2.4.1):
- Tính theo khóa (course basis), mỗi khóa có học phí riêng
- Học viên đóng toàn bộ một lần khi enrollment
- Khuyến mãi: Original_Price - Discount_Amount = Final_Price
- Phát hành biên lai/hóa đơn cho mỗi giao dịch
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Tuple
from uuid import UUID
from decimal import Decimal
from fastapi import HTTPException

from app.models.finance import Invoice, InvoiceStatus
from app.models.academic import ClassEnrollment, Class, Course
from app.models.user import User, UserRole
from app.schemas.finance.invoice import InvoiceCreate, InvoiceResponse


class InvoiceService:

    def create_invoice(self, db: Session, payload: InvoiceCreate, created_by_id: UUID) -> InvoiceResponse:
        """
        Tạo hóa đơn mới cho enrollment.
        - Validate enrollment_id tồn tại và chưa có invoice PENDING/PAID
        - Tính original_amount từ course fee (qua enrollment → class → course)
        - Áp discount nếu có
        - Persist Invoice với status=PENDING
        """
        # 1. Validate enrollment tồn tại
        enrollment = db.query(ClassEnrollment).filter(
            ClassEnrollment.id == payload.enrollment_id,
        ).first()
        if not enrollment:
            raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký khóa học")

        # 2. Kiểm tra chưa có invoice PENDING/PAID cho enrollment này
        existing_invoice = db.query(Invoice).filter(
            Invoice.enrollment_id == payload.enrollment_id,
            Invoice.status.in_([InvoiceStatus.PENDING.value, InvoiceStatus.PAID.value]),
        ).first()
        if existing_invoice:
            raise HTTPException(
                status_code=409,
                detail="Đăng ký này đã có hóa đơn đang chờ hoặc đã thanh toán",
            )

        # 3. Tính original_amount từ class fee (class có fee_amount riêng)
        class_obj = db.query(Class).filter(Class.id == enrollment.class_id).first()
        if not class_obj:
            raise HTTPException(status_code=404, detail="Không tìm thấy lớp học liên quan")

        original_amount = Decimal(str(class_obj.fee_amount))
        discount_amount = payload.discount_amount or Decimal("0")

        if discount_amount > original_amount:
            raise HTTPException(status_code=400, detail="Giảm giá không thể lớn hơn học phí gốc")

        final_amount = original_amount - discount_amount

        # 4. Persist Invoice
        invoice = Invoice(
            student_id=enrollment.student_id,
            enrollment_id=payload.enrollment_id,
            original_amount=original_amount,
            discount_amount=discount_amount,
            final_amount=final_amount,
            status=InvoiceStatus.PENDING,
            due_date=payload.due_date,
            notes=payload.notes,
            extra_metadata=payload.extra_metadata or {},
            created_by=created_by_id,
        )
        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        return InvoiceResponse.model_validate(invoice)

    # ------------------------------------------------------------------
    # Helper: enrich Invoice rows with student_name & course_name
    # ------------------------------------------------------------------
    def _enrich_invoices(
        self, db: Session, invoices: list[Invoice]
    ) -> List[InvoiceResponse]:
        """Attach student_name and course_name to each invoice."""
        if not invoices:
            return []

        # Collect IDs
        student_ids = {inv.student_id for inv in invoices}
        enrollment_ids = {inv.enrollment_id for inv in invoices}

        # Batch-load student names
        students = (
            db.query(User.id, User.first_name, User.last_name)
            .filter(User.id.in_(student_ids))
            .all()
        )
        student_map = {
            s.id: f"{s.last_name} {s.first_name}" for s in students
        }

        # Batch-load course names via enrollment → class → course
        enrollment_courses = (
            db.query(ClassEnrollment.id, Course.name)
            .join(Class, Class.id == ClassEnrollment.class_id)
            .join(Course, Course.id == Class.course_id)
            .filter(ClassEnrollment.id.in_(enrollment_ids))
            .all()
        )
        course_map = {ec.id: ec.name for ec in enrollment_courses}

        results: List[InvoiceResponse] = []
        for inv in invoices:
            resp = InvoiceResponse.model_validate(inv)
            resp.student_name = student_map.get(inv.student_id)
            resp.course_name = course_map.get(inv.enrollment_id)
            results.append(resp)
        return results

    def list_all_invoices(
        self, db: Session, status: str | None, student_id: UUID | None,
        page: int, limit: int,
    ) -> Tuple[List[InvoiceResponse], int]:
        """Admin xem tất cả hóa đơn (phân trang, lọc tùy chọn)."""
        query = db.query(Invoice).filter(Invoice.deleted_at.is_(None))

        if status:
            query = query.filter(Invoice.status == status)
        if student_id:
            query = query.filter(Invoice.student_id == student_id)

        total = query.count()
        items = (
            query
            .order_by(Invoice.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return self._enrich_invoices(db, items), total

    def list_my_invoices(
        self, db: Session, student_id: UUID, page: int, limit: int
    ) -> Tuple[List[InvoiceResponse], int]:
        """Học viên xem danh sách hóa đơn của mình (phân trang)."""
        query = db.query(Invoice).filter(
            Invoice.student_id == student_id,
            Invoice.deleted_at.is_(None),
        )
        total = query.count()
        items = (
            query
            .order_by(Invoice.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )
        return self._enrich_invoices(db, items), total

    def get_invoice_detail(
        self, db: Session, invoice_id: UUID, current_user: User
    ) -> InvoiceResponse:
        """
        Xem chi tiết hóa đơn.
        - Raise 404 nếu không tồn tại
        - Raise 403 nếu student cố xem hóa đơn của người khác
        """
        invoice = db.query(Invoice).filter(
            Invoice.id == invoice_id,
            Invoice.deleted_at.is_(None),
        ).first()
        if not invoice:
            raise HTTPException(status_code=404, detail="Không tìm thấy hóa đơn")

        # Student chỉ xem được hóa đơn của mình
        if (
            current_user.role == UserRole.STUDENT
            and invoice.student_id != current_user.id
        ):
            raise HTTPException(status_code=403, detail="Bạn không có quyền xem hóa đơn này")

        return self._enrich_invoices(db, [invoice])[0]


invoice_service = InvoiceService()
