"""
Report Schemas
Dựa trên model ReportExportJob (app/models/finance.py) và note trong router report.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal

from app.models.finance import ReportType, ExportJobStatus


# ---------------------------------------------------------------------------
# Revenue report
# ---------------------------------------------------------------------------

class CourseRevenueBreakdown(BaseModel):
    """Breakdown doanh thu theo từng khóa/lớp (khi group_by_course=True)."""
    course_id: UUID
    course_name: str
    total_revenue: Decimal
    total_invoices: int


class RevenueReportResponse(BaseModel):
    """GET /reports/revenue"""
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    total_revenue: Decimal = Field(..., description="Tổng doanh thu (payments SUCCESS)")
    total_invoices: int = Field(..., description="Tổng số hóa đơn đã thanh toán")
    avg_payment_value: Decimal = Field(..., description="Giá trị thanh toán trung bình")

    breakdown_by_course: Optional[List[CourseRevenueBreakdown]] = Field(
        None, description="Breakdown theo khóa học (nếu group_by_course=True)"
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Expenses report
# ---------------------------------------------------------------------------

class ExpenseCategoryBreakdown(BaseModel):
    """Breakdown chi phí theo category."""
    category: str
    total: Decimal


class ExpensesReportResponse(BaseModel):
    """GET /reports/expenses"""
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    cost_type: Optional[str] = None

    total_expenses: Decimal = Field(..., description="Tổng chi phí")
    breakdown_by_category: List[ExpenseCategoryBreakdown] = Field(
        default_factory=list, description="Breakdown theo loại chi phí"
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Profit report
# ---------------------------------------------------------------------------

class MonthlyTrend(BaseModel):
    """Trend lợi nhuận theo tháng."""
    month: str = Field(..., description="YYYY-MM")
    revenue: Decimal
    expenses: Decimal
    profit: Decimal


class ProfitReportResponse(BaseModel):
    """GET /reports/profit"""
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    total_revenue: Decimal
    total_expenses: Decimal
    profit: Decimal = Field(..., description="= total_revenue - total_expenses")
    profit_margin: Decimal = Field(..., description="= profit / total_revenue * 100")

    monthly_trends: Optional[List[MonthlyTrend]] = Field(
        None, description="Month-over-month trend (nếu range > 1 tháng)"
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Debt report
# ---------------------------------------------------------------------------

class DebtListResponse(BaseModel):
    """GET /reports/debts – thông tin học viên nợ phí."""
    invoice_id: UUID
    student_id: UUID
    student_name: str
    student_email: Optional[str] = None

    final_amount: Decimal = Field(..., description="Số tiền cần thanh toán")
    due_date: Optional[datetime] = None
    days_overdue: int = Field(..., description="Số ngày quá hạn")

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Export job
# ---------------------------------------------------------------------------

class ExportJobCreate(BaseModel):
    """POST /reports/export-jobs – khởi tạo job xuất báo cáo."""
    report_type: ReportType = Field(..., description="Loại báo cáo cần xuất")
    filters: Optional[dict] = Field(
        default=None,
        description="date_from, date_to, group_by, cost_type, v.v."
    )


class ExportJobResponse(BaseModel):
    """Thông tin export job."""
    id: UUID
    report_type: ReportType
    status: ExportJobStatus

    filters: Optional[dict] = None
    file_url: Optional[str] = Field(None, description="Link download khi completed")
    error_message: Optional[str] = Field(None, description="Chi tiết lỗi nếu failed")

    created_by: Optional[UUID] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
