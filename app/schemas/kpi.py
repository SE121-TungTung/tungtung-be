from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional
from datetime import datetime
from uuid import UUID
import re
import enum
from app.models.kpi import ContractType, JobStatus, ActiveStatus

# -------------------------------------------------------------------
# 1. BẬC KPI (KpiTier)
# -------------------------------------------------------------------

class KpiTierBase(BaseModel):
    tier_name: str = Field(..., max_length=20, description="Tên bậc KPI (A, B, C, D)")
    min_score: float = Field(..., ge=0, description="Điểm tối thiểu")
    max_score: float = Field(..., le=100, description="Điểm tối đa")
    reward_percentage: float = Field(..., ge=0, description="Phần trăm thưởng (%)")
    status: ActiveStatus = Field(default=ActiveStatus.ACTIVE, description="Trạng thái kích hoạt")

class KpiTierUpdate(KpiTierBase):
    id: Optional[int] = Field(default=None, description="ID của bậc (Truyền ID nếu là cập nhật, bỏ trống nếu tạo mới)")

class KpiTierResponse(KpiTierBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)

# -------------------------------------------------------------------
# 2. CẤU HÌNH LƯƠNG GIÁO VIÊN (TeacherPayrollConfig)
# -------------------------------------------------------------------

class TeacherPayrollConfigUpdate(BaseModel):
    contract_type: ContractType = Field(..., description="Loại hợp đồng")
    base_salary: float = Field(default=0, ge=0, description="Lương cơ bản")
    lesson_rate: float = Field(default=0, ge=0, description="Đơn giá tiết dạy")
    max_kpi_bonus: float = Field(default=0, ge=0, description="Quỹ thưởng KPI tối đa (nếu fix cứng cho GV này)")
    fixed_allowance: float = Field(default=0, ge=0, description="Phụ cấp cố định (xăng xe, điện thoại...)")

class TeacherPayrollConfigResponse(TeacherPayrollConfigUpdate):
    teacher_id: int
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# -------------------------------------------------------------------
# 3. TIẾN TRÌNH TÍNH LƯƠNG (KpiCalculationJob)
# -------------------------------------------------------------------

class KpiCalculationJobCreate(BaseModel):
    period: str = Field(..., description="Kỳ lương cần tính toán (Định dạng YYYY-MM)")

    @field_validator('period')
    @classmethod
    def validate_period_format(cls, v: str) -> str:
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", v):
            raise ValueError('Kỳ lương phải theo định dạng YYYY-MM (Ví dụ: 2026-03)')
        return v

class KpiCalculationJobResponse(BaseModel):
    job_id: UUID
    period: str
    status: JobStatus
    total_teachers: int
    processed_count: int
    error_log: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

# -------------------------------------------------------------------
# 4. KẾT QUẢ KPI HÀNG THÁNG (TeacherMonthlyKpi)
# -------------------------------------------------------------------

class KpiCriteriaScoreItem(BaseModel):
    code: str = Field(..., description="Mã tiêu chí (VD: ATTENDANCE)")
    score: float = Field(..., ge=0, description="Điểm đạt được")
    max_score: float = Field(..., gt=0, description="Điểm tối đa của tiêu chí này")

class KpiDetails(BaseModel):
    criteria_scores: List[KpiCriteriaScoreItem] = Field(..., description="Danh sách điểm chi tiết từng tiêu chí")

class TeacherMonthlyKpiResponse(BaseModel):
    id: int
    teacher_id: int
    period: str
    total_score: float
    kpi_tier_id: Optional[int] = None
    kpi_details: KpiDetails
    calculated_bonus: float
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)