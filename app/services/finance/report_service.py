"""
Report Service
Business logic cho Report module.

Doc reference (2.4.3 – Báo cáo Tài chính):
1. Revenue Report: tổng doanh thu, theo khóa, theo lớp, ròng (sau hoàn tiền)
2. Expense Report: lương GV, breakdown full-time/part-time/native, thưởng KPI
3. Profit Report: Net profit = Revenue - Expense, profit margin
4. Payment Status: học viên nợ, GV chưa nhận lương, hoàn tiền đang xử lý
   → Router note chỉ có "debts" (học viên nợ). Doc bổ sung thêm GV chưa
     nhận lương + hoàn tiền đang xử lý, nhưng endpoint hiện tại chỉ có /debts.
     → Implement đúng theo router endpoint hiện có.

Export: Excel, CSV, PDF
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, case, extract
from typing import List, Tuple, Optional
from uuid import UUID
from datetime import date, datetime, timezone
from decimal import Decimal
from fastapi import BackgroundTasks, HTTPException

from app.models.finance import (
    Invoice, InvoiceStatus,
    Payment, PaymentStatus,
    Refund, RefundStatus,
    ReportExportJob, ReportType, ExportJobStatus,
)
from app.models.academic import ClassEnrollment, Class, Course
from app.models.kpi import Salary, SalaryStatus, ContractType
from app.models.user import User

from app.schemas.finance.report import (
    RevenueReportResponse,
    CourseRevenueBreakdown,
    ExpensesReportResponse,
    ExpenseCategoryBreakdown,
    ProfitReportResponse,
    MonthlyTrend,
    DebtListResponse,
    ExportJobCreate,
    ExportJobResponse,
)


class ReportService:

    # -------------------------------------------------------------------
    # GET /reports/revenue
    # -------------------------------------------------------------------
    def get_revenue_report(
        self,
        db: Session,
        date_from: Optional[date],
        date_to: Optional[date],
        group_by_course: bool,
    ) -> RevenueReportResponse:
        """
        Aggregate payments SUCCESS trong khoảng thời gian.
        Doc: Tổng doanh thu, theo khóa, ròng (sau hoàn tiền).
        """
        query = db.query(Payment).filter(Payment.status == PaymentStatus.SUCCESS)

        if date_from:
            query = query.filter(func.date(Payment.paid_at) >= date_from)
        if date_to:
            query = query.filter(func.date(Payment.paid_at) <= date_to)

        # Aggregate
        result = query.with_entities(
            func.coalesce(func.sum(Payment.amount), 0).label("total_revenue"),
            func.count(Payment.id).label("total_invoices"),
        ).first()

        total_revenue = Decimal(str(result.total_revenue))
        total_invoices = result.total_invoices
        avg_payment_value = (
            (total_revenue / total_invoices).quantize(Decimal("0.01"))
            if total_invoices > 0
            else Decimal("0")
        )

        # Trừ hoàn tiền (doanh thu ròng) — theo doc
        refund_query = db.query(
            func.coalesce(func.sum(Refund.approved_amount), 0)
        ).filter(
            Refund.status.in_([RefundStatus.APPROVED, RefundStatus.PROCESSED]),
        )
        if date_from:
            refund_query = refund_query.filter(func.date(Refund.reviewed_at) >= date_from)
        if date_to:
            refund_query = refund_query.filter(func.date(Refund.reviewed_at) <= date_to)
        total_refunds = Decimal(str(refund_query.scalar() or 0))
        net_revenue = total_revenue - total_refunds

        # Breakdown by course nếu yêu cầu
        breakdown = None
        if group_by_course:
            breakdown = self._revenue_by_course(db, date_from, date_to)

        return RevenueReportResponse(
            date_from=date_from,
            date_to=date_to,
            total_revenue=net_revenue,
            total_invoices=total_invoices,
            avg_payment_value=avg_payment_value,
            breakdown_by_course=breakdown,
        )

    # -------------------------------------------------------------------
    # GET /reports/expenses
    # -------------------------------------------------------------------
    def get_expenses_report(
        self,
        db: Session,
        date_from: Optional[date],
        date_to: Optional[date],
        cost_type: Optional[str],
    ) -> ExpensesReportResponse:
        """
        Doc: Tổng lương GV, breakdown full-time/part-time/native, thưởng KPI.
        cost_type: SALARY | ALL (hiện tại chỉ hỗ trợ salary-based expenses)
        """
        salary_query = db.query(Salary)

        # Filter theo khoảng thời gian (period: YYYY-MM)
        if date_from:
            salary_query = salary_query.filter(Salary.period >= date_from.strftime("%Y-%m"))
        if date_to:
            salary_query = salary_query.filter(Salary.period <= date_to.strftime("%Y-%m"))

        # Breakdown theo contract type (doc: full-time vs part-time)
        breakdown_rows = (
            salary_query
            .with_entities(
                Salary.contract_type,
                func.coalesce(func.sum(Salary.net_salary), 0).label("total"),
            )
            .group_by(Salary.contract_type)
            .all()
        )

        breakdown = []
        total_expenses = Decimal("0")
        for row in breakdown_rows:
            amount = Decimal(str(row.total))
            total_expenses += amount
            breakdown.append(ExpenseCategoryBreakdown(
                category=row.contract_type.value if row.contract_type else "UNKNOWN",
                total=amount,
            ))

        # Thêm tổng thưởng KPI riêng biệt
        kpi_bonus_total = (
            salary_query
            .with_entities(func.coalesce(func.sum(Salary.kpi_bonus_calc), 0))
            .scalar()
        )
        if kpi_bonus_total:
            breakdown.append(ExpenseCategoryBreakdown(
                category="KPI_BONUS",
                total=Decimal(str(kpi_bonus_total)),
            ))

        return ExpensesReportResponse(
            date_from=date_from,
            date_to=date_to,
            cost_type=cost_type,
            total_expenses=total_expenses,
            breakdown_by_category=breakdown,
        )

    # -------------------------------------------------------------------
    # GET /reports/profit
    # -------------------------------------------------------------------
    def get_profit_report(
        self,
        db: Session,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> ProfitReportResponse:
        """
        Doc: Net profit = Revenue - Expense (lương + chi phí khác), Profit margin.
        """
        revenue_data = self.get_revenue_report(db, date_from, date_to, group_by_course=False)
        expenses_data = self.get_expenses_report(db, date_from, date_to, cost_type="ALL")

        total_revenue = revenue_data.total_revenue
        total_expenses = expenses_data.total_expenses
        profit = total_revenue - total_expenses
        profit_margin = (
            (profit / total_revenue * 100).quantize(Decimal("0.01"))
            if total_revenue > 0
            else Decimal("0")
        )

        # Monthly trends nếu có khoảng thời gian
        monthly_trends = None
        if date_from and date_to and date_from < date_to:
            monthly_trends = self._monthly_trends(db, date_from, date_to)

        return ProfitReportResponse(
            date_from=date_from,
            date_to=date_to,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            profit=profit,
            profit_margin=profit_margin,
            monthly_trends=monthly_trends,
        )

    # -------------------------------------------------------------------
    # GET /reports/debts
    # -------------------------------------------------------------------
    def get_debt_report(
        self, db: Session, page: int, limit: int
    ) -> Tuple[List[DebtListResponse], int]:
        """
        Doc (Payment Status): Học viên nợ (chưa thanh toán).
        Query Invoice status=PENDING mà due_date < now().
        """
        now = datetime.now(timezone.utc)

        query = (
            db.query(Invoice, User)
            .join(User, User.id == Invoice.student_id)
            .filter(
                Invoice.status == InvoiceStatus.PENDING,
                Invoice.due_date.isnot(None),
                Invoice.due_date < now,
                Invoice.deleted_at.is_(None),
            )
            .order_by(Invoice.final_amount.desc())
        )

        total = query.count()
        rows = query.offset((page - 1) * limit).limit(limit).all()

        items = []
        for invoice, user in rows:
            days_overdue = (now - invoice.due_date).days if invoice.due_date else 0
            items.append(DebtListResponse(
                invoice_id=invoice.id,
                student_id=user.id,
                student_name=f"{user.first_name} {user.last_name}",
                student_email=user.email,
                final_amount=invoice.final_amount,
                due_date=invoice.due_date,
                days_overdue=max(days_overdue, 0),
            ))

        return items, total

    # -------------------------------------------------------------------
    # POST /reports/export-jobs
    # -------------------------------------------------------------------
    def create_export_job(
        self,
        db: Session,
        payload: ExportJobCreate,
        created_by: UUID,
        bg_tasks: BackgroundTasks,
    ) -> ExportJobResponse:
        """
        Tạo job xuất báo cáo bất đồng bộ.
        Doc: Export format Excel, CSV, PDF.
        """
        job = ReportExportJob(
            report_type=payload.report_type,
            status=ExportJobStatus.PENDING,
            filters=payload.filters or {},
            created_by=created_by,
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # Enqueue background task
        bg_tasks.add_task(self._process_export, job.id)

        return ExportJobResponse.model_validate(job)

    # ===================================================================
    # Private helpers
    # ===================================================================

    def _revenue_by_course(
        self, db: Session, date_from: Optional[date], date_to: Optional[date]
    ) -> List[CourseRevenueBreakdown]:
        """Breakdown doanh thu theo khóa học."""
        query = (
            db.query(
                Course.id.label("course_id"),
                Course.name.label("course_name"),
                func.coalesce(func.sum(Payment.amount), 0).label("total_revenue"),
                func.count(Payment.id).label("total_invoices"),
            )
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .join(ClassEnrollment, ClassEnrollment.id == Invoice.enrollment_id)
            .join(Class, Class.id == ClassEnrollment.class_id)
            .join(Course, Course.id == Class.course_id)
            .filter(Payment.status == PaymentStatus.SUCCESS)
        )

        if date_from:
            query = query.filter(func.date(Payment.paid_at) >= date_from)
        if date_to:
            query = query.filter(func.date(Payment.paid_at) <= date_to)

        rows = query.group_by(Course.id, Course.name).all()

        return [
            CourseRevenueBreakdown(
                course_id=row.course_id,
                course_name=row.course_name,
                total_revenue=Decimal(str(row.total_revenue)),
                total_invoices=row.total_invoices,
            )
            for row in rows
        ]

    def _monthly_trends(
        self, db: Session, date_from: date, date_to: date
    ) -> List[MonthlyTrend]:
        """Month-over-month revenue/expense/profit trends."""
        # Revenue by month
        rev_rows = (
            db.query(
                func.to_char(Payment.paid_at, "YYYY-MM").label("month"),
                func.coalesce(func.sum(Payment.amount), 0).label("revenue"),
            )
            .filter(
                Payment.status == PaymentStatus.SUCCESS,
                func.date(Payment.paid_at) >= date_from,
                func.date(Payment.paid_at) <= date_to,
            )
            .group_by(func.to_char(Payment.paid_at, "YYYY-MM"))
            .all()
        )
        revenue_map = {r.month: Decimal(str(r.revenue)) for r in rev_rows}

        # Expenses by month (salary period = YYYY-MM)
        exp_rows = (
            db.query(
                Salary.period.label("month"),
                func.coalesce(func.sum(Salary.net_salary), 0).label("expenses"),
            )
            .filter(
                Salary.period >= date_from.strftime("%Y-%m"),
                Salary.period <= date_to.strftime("%Y-%m"),
            )
            .group_by(Salary.period)
            .all()
        )
        expense_map = {e.month: Decimal(str(e.expenses)) for e in exp_rows}

        # Merge months
        all_months = sorted(set(list(revenue_map.keys()) + list(expense_map.keys())))
        trends = []
        for month in all_months:
            rev = revenue_map.get(month, Decimal("0"))
            exp = expense_map.get(month, Decimal("0"))
            trends.append(MonthlyTrend(
                month=month,
                revenue=rev,
                expenses=exp,
                profit=rev - exp,
            ))
        return trends

    def _process_export(self, job_id: UUID):
        """
        Background task: generate export file.
        Trong production sẽ dùng openpyxl/reportlab rồi upload S3.
        """
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            job = db.query(ReportExportJob).filter(ReportExportJob.id == job_id).first()
            if not job:
                return

            job.status = ExportJobStatus.PROCESSING
            db.commit()

            # Stub: giả lập tạo file
            # Thực tế sẽ query data theo job.report_type + job.filters,
            # generate file (Excel/CSV/PDF), upload S3, lấy presigned URL
            import time
            time.sleep(1)  # Simulate processing

            job.status = ExportJobStatus.COMPLETED
            job.file_url = f"/exports/{job.id}.xlsx"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

        except Exception as e:
            job = db.query(ReportExportJob).filter(ReportExportJob.id == job_id).first()
            if job:
                job.status = ExportJobStatus.FAILED
                job.error_message = str(e)
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        finally:
            db.close()


report_service = ReportService()
