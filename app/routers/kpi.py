from fastapi import APIRouter, Depends, HTTPException, Query, Path, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.core.database import get_db

from app.schemas.base_schema import ApiResponse

from app.schemas.kpi import (
    KpiTierResponse, KpiTierUpdate, 
    KpiCalculationJobCreate, KpiCalculationJobResponse,
    TeacherMonthlyKpiResponse, TeacherPayrollConfigUpdate, TeacherPayrollConfigResponse
)

router = APIRouter(prefix="/api/v1", tags=["KPI & Payroll"])

# --- 1 & 2. Cấu hình Bậc KPI (System Settings) ---

@router.get("/settings/kpi-tiers", response_model=ApiResponse[List[KpiTierResponse]])
async def get_kpi_tiers(db: Session = Depends(get_db)):
    """Lấy danh sách cấu hình các bậc KPI (A, B, C, D)"""
    # TODO: Gọi hàm service query DB: db.query(KpiTier).all()
    tiers = [] # Placeholder: thay bằng dữ liệu thực tế
    
    return ApiResponse(
        success=True, 
        data=tiers, 
        message="Lấy danh sách bậc KPI thành công"
    )

@router.put("/settings/kpi-tiers", response_model=ApiResponse[List[KpiTierResponse]])
async def update_kpi_tiers(
    payload: List[KpiTierUpdate], 
    db: Session = Depends(get_db)
):
    """Cập nhật hàng loạt cấu hình bậc KPI (Cần check overlap khoảng điểm ở đây)"""
    # TODO: Validate No Overlap, update DB, commit
    updated_tiers = [] # Placeholder: thay bằng dữ liệu sau khi update
    
    return ApiResponse(
        success=True, 
        data=updated_tiers, 
        message="Cập nhật cấu hình bậc KPI thành công"
    )


# --- 3 & 4. Tiến trình tính lương (Calculation Jobs) ---

@router.post("/kpi/calculation-jobs", response_model=ApiResponse[KpiCalculationJobResponse])
async def create_kpi_calculation_job(
    payload: KpiCalculationJobCreate, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    """Khởi tạo tiến trình tính KPI tháng (Chạy bất đồng bộ)"""
    # TODO: 
    # 1. Tạo bản ghi job trong DB với status = PENDING
    # 2. background_tasks.add_task(calculate_monthly_kpi_service, job_id, payload.period, db)
    
    job_info = None # Placeholder
    
    return ApiResponse(
        success=True, 
        data=job_info, 
        message=f"Đã khởi tạo tiến trình tính KPI cho kỳ {payload.period}"
    )

@router.get("/kpi/calculation-jobs/{job_id}", response_model=ApiResponse[KpiCalculationJobResponse])
async def get_kpi_calculation_job(
    job_id: UUID = Path(..., description="UUID của tiến trình"), 
    db: Session = Depends(get_db)
):
    """Kiểm tra tiến độ tính KPI"""
    # TODO: Query DB lấy thông tin job
    job_info = None # Placeholder
    
    if not job_info:
        raise HTTPException(status_code=404, detail="Không tìm thấy tiến trình này")
        
    return ApiResponse(
        success=True, 
        data=job_info, 
        message="Thành công"
    )


# --- 5 & 6. Dữ liệu Giáo viên (Teacher KPI & Payroll) ---

@router.get("/teachers/{teacher_id}/kpi", response_model=ApiResponse[TeacherMonthlyKpiResponse])
async def get_teacher_monthly_kpi(
    teacher_id: int = Path(..., description="ID của giáo viên"),
    period: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Kỳ lương YYYY-MM"),
    db: Session = Depends(get_db)
):
    """Lấy chi tiết điểm KPI của giáo viên trong một tháng"""
    # TODO: Query DB bảng teacher_monthly_kpis lọc theo teacher_id và period
    kpi_data = None # Placeholder
    
    if not kpi_data:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy KPI kỳ {period} của giáo viên này")
        
    return ApiResponse(
        success=True, 
        data=kpi_data, 
        message="Lấy dữ liệu KPI thành công"
    )

@router.put("/teachers/{teacher_id}/payroll-config", response_model=ApiResponse[TeacherPayrollConfigResponse])
async def update_teacher_payroll_config(
    payload: TeacherPayrollConfigUpdate,
    teacher_id: int = Path(..., description="ID của giáo viên"),
    db: Session = Depends(get_db)
):
    """Cấu hình lương cơ bản, đơn giá tiết, phụ cấp cố định cho giáo viên"""
    # TODO: Update DB bảng teacher_payroll_configs
    updated_config = None # Placeholder
    
    return ApiResponse(
        success=True, 
        data=updated_config, 
        message="Cập nhật cấu hình lương giáo viên thành công"
    )