from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from fastapi import HTTPException, status
from datetime import datetime
from decimal import Decimal
import logging

from app.core.database import SessionLocal
from app.core.exceptions import APIException
from app.models.kpi import KpiTier, KpiCalculationJob, TeacherMonthlyKpi, TeacherPayrollConfig, KpiCriteria, JobStatus
from app.models.user import User, UserRole
from app.models.session_attendance import ClassSession, SessionStatus
from app.schemas.kpi import KpiTierUpdate, KpiCalculationJobCreate

from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)

class KpiSettingsService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_tiers(self):
        return self.db.query(KpiTier).order_by(KpiTier.min_score.asc()).all()

    def bulk_update_tiers(self, tiers_payload: List['KpiTierUpdate']):
        """
        Nghiệp vụ: 
        1. Phải có dữ liệu.
        2. min_score phải < max_score.
        3. Các mốc điểm không được chồng chéo (overlap) hoặc có khoảng trống (gap).
        """
        if not tiers_payload:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dữ liệu cấu hình trống")

        # Sắp xếp theo min_score tăng dần
        sorted_tiers = sorted(tiers_payload, key=lambda x: x.min_score)

        # Validate logic nghiệp vụ
        for i in range(len(sorted_tiers)):
            current = sorted_tiers[i]
            
            if current.min_score >= current.max_score:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Bậc {current.tier_name} có min_score lớn hơn hoặc bằng max_score"
                )
                
            # Kiểm tra gap/overlap với tier tiếp theo
            if i < len(sorted_tiers) - 1:
                next_tier = sorted_tiers[i+1]
                if current.max_score > next_tier.min_score:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Chồng chéo điểm giữa bậc {current.tier_name} và {next_tier.tier_name}"
                    )
                if current.max_score < next_tier.min_score:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Có khoảng trống điểm giữa bậc {current.tier_name} và {next_tier.tier_name}"
                    )

        try:
            # Logic DB: Thường cấu hình hệ thống người ta hay xóa cũ insert mới cho nhanh
            # self.db.query(KpiTier).delete()
            # new_tiers = [KpiTier(**t.model_dump()) for t in sorted_tiers]
            # self.db.add_all(new_tiers)
            # self.db.commit()
            
            # return new_tiers
            return sorted_tiers # Dữ liệu mô phỏng trả về
        except Exception as e:
            self.db.rollback()
            raise APIException(status_code=500, code="INTERNAL_SERVER_ERROR", message="Đã có lỗi xảy ra khi cập nhật cấu hình bậc KPI")


class KpiCalculationService:
    def __init__(self, db: Session):
        self.db = db

    def trigger_calculation_job(self, payload: 'KpiCalculationJobCreate', bg_tasks: 'BackgroundTasks'):
        """Kiểm tra và khởi tạo tiến trình tính lương"""
        
        # 1. Business logic: Check xem tháng này đã tính hoặc đang tính chưa?
        existing_job = self.db.query(KpiCalculationJob).filter(
            KpiCalculationJob.period == payload.period,
            KpiCalculationJob.status.in_(['PENDING', 'PROCESSING'])
        ).first()
        
        if existing_job:
            raise APIException(
                status_code=409,
                code="JOB_ALREADY_EXISTS", 
                detail=f"Tiến trình tính lương cho kỳ {payload.period} đang diễn ra."
            )

        # 2. Tạo job mới
        new_job = KpiCalculationJob(period=payload.period, status="PENDING")
        self.db.add(new_job)
        self.db.commit()
        self.db.refresh(new_job)
        
        job_id = new_job.job_id

        # 3. Đẩy task vào background chạy ngầm
        bg_tasks.add_task(self._execute_calculation, job_id, payload.period)

        return {"job_id": job_id, "period": payload.period, "status": "PENDING"}

    async def _execute_calculation(self, job_id: UUID, period: str):
        """
        Hàm này chạy dưới background. Không nên inject self.db trực tiếp từ API request 
        vì session có thể bị đóng sau khi API trả response.
        Cần tạo một DB session mới bên trong hàm này.
        """
        db = SessionLocal() # Khởi tạo session mới
        try:
            # 1. Update trạng thái: PENDING -> PROCESSING
            current_job = db.query(KpiCalculationJob).filter(KpiCalculationJob.job_id == job_id).first()
            if not current_job:
                # Log lỗi: Không tìm thấy job
                logger.error(f"KPI Calculation Job {job_id} not found")
                return
            current_job.status = JobStatus.PROCESSING
            db.commit()


            # 2. Lấy Teacher -> Tính toán -> Lưu TeacherMonthlyKpi
            # Lấy tất cả giáo viên (User với role=TEACHER)
            teachers = db.query(User).filter(User.role == UserRole.TEACHER).all()
            current_job.total_teachers = len(teachers)
            db.commit()
            
            processed_count = 0
            errors = []
            
            for teacher in teachers:
                try:
                    self._calculate_teacher_kpi(db, teacher.id, period, current_job)
                    processed_count += 1
                    current_job.processed_count = processed_count
                    db.commit()
                except Exception as e:
                    error_msg = f"Error calculating KPI for teacher {teacher.id}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
            
            # 3. Update trạng thái: PROCESSING -> COMPLETED
            current_job.status = JobStatus.COMPLETED
            current_job.finished_at = datetime.utcnow()
            if errors:
                current_job.error_log = "\n".join(errors)
            db.commit()
            
            logger.info(f"KPI Calculation Job {job_id} completed. Processed {processed_count}/{len(teachers)} teachers")
            
        except Exception as e:
            # 4. Update trạng thái: PROCESSING -> FAILED kèm error log
            logger.error(f"KPI Calculation Job {job_id} failed: {str(e)}", exc_info=True)
            try:
                current_job = db.query(KpiCalculationJob).filter(KpiCalculationJob.job_id == job_id).first()
                if current_job:
                    current_job.status = JobStatus.FAILED
                    current_job.error_log = str(e)
                    current_job.finished_at = datetime.utcnow()
                    db.commit()
            except:
                pass
        finally:
            db.close()
    
    def _calculate_teacher_kpi(self, db: Session, teacher_id: int, period: str, job):
        """
        Tính điểm KPI cho một giáo viên trong một kỳ.
        
        Logic tính toán:
        1. Lấy các tiêu chí KPI
        2. Tính điểm cho mỗi tiêu chí
        3. Tính tổng điểm (weighted average)
        4. Xác định bậc KPI dựa trên điểm
        5. Tính thưởng KPI dựa trên bậc
        6. Lưu kết quả vào DB
        """
        
        # Kiểm tra xem đã tính cho kỳ này chưa
        existing_kpi = db.query(TeacherMonthlyKpi).filter(
            TeacherMonthlyKpi.teacher_id == teacher_id,
            TeacherMonthlyKpi.period == period
        ).first()
        
        if existing_kpi:
            return  # Skip nếu đã tính rồi
        
        # Lấy cấu hình lương giáo viên
        payroll_config = db.query(TeacherPayrollConfig).filter(
            TeacherPayrollConfig.teacher_id == teacher_id
        ).first()
        
        if not payroll_config:
            raise ValueError(f"No payroll config found for teacher {teacher_id}")
        
        # Lấy tất cả tiêu chí KPI
        criteria_list = db.query(KpiCriteria).all()
        
        # Tính điểm cho mỗi tiêu chí
        criteria_scores = []
        total_weighted_score = Decimal(0)
        total_weight = Decimal(0)
        
        for criteria in criteria_list:
            # Tính điểm cho tiêu chí này
            score = self._calculate_criteria_score(db, teacher_id, period, criteria)
            
            criteria_scores.append({
                "code": criteria.criteria_code,
                "score": float(score),
                "max_score": 100.0  # Mỗi tiêu chí có max 100 điểm
            })
            
            # Tính weighted score
            weight = Decimal(criteria.weight_percent)
            total_weighted_score += score * weight / 100
            total_weight += weight
        
        # Normalize điểm tổng về thang 0-100
        if total_weight > 0:
            total_score = total_weighted_score / total_weight * 100
        else:
            total_score = Decimal(0)
        
        total_score = float(total_score)
        
        # Xác định bậc KPI dựa trên điểm
        kpi_tier = db.query(KpiTier).filter(
            KpiTier.min_score <= total_score,
            KpiTier.max_score >= total_score
        ).first()
        
        # Tính thưởng KPI
        calculated_bonus = Decimal(0)
        if kpi_tier and payroll_config.max_kpi_bonus:
            bonus_percentage = Decimal(kpi_tier.reward_percentage)
            calculated_bonus = Decimal(payroll_config.max_kpi_bonus) * bonus_percentage / 100
        
        # Tạo bản ghi TeacherMonthlyKpi
        teacher_kpi = TeacherMonthlyKpi(
            teacher_id=teacher_id,
            period=period,
            total_score=Decimal(str(total_score)),
            kpi_tier_id=kpi_tier.id if kpi_tier else None,
            kpi_details={"criteria_scores": criteria_scores},
            calculated_bonus=calculated_bonus
        )
        
        db.add(teacher_kpi)
        db.flush()  # Flush để get ID nhưng chưa commit
    
    def _calculate_criteria_score(self, db: Session, teacher_id: int, period: str, criteria) -> Decimal:
        """
        Tính điểm cho một tiêu chí KPI cụ thể.
        
        Hiện tại hỗ trợ các tiêu chí:
        - ATTENDANCE: Tỉ lệ tham gia dạy trong kỳ
        - LESSON_COMPLETION: Hoàn thành tiết học theo lịch
        - STUDENT_SATISFACTION: Mức độ hài lòng của học viên (từ survey)
        
        Có thể mở rộng thêm các tiêu chí khác.
        """
        
        criteria_code = criteria.criteria_code
        
        if criteria_code == "ATTENDANCE":
            # Tính tỉ lệ tham gia dạy
            # Lấy số buổi học lên lịch của giáo viên trong kỳ
            period_year, period_month = period.split('-')
            
            scheduled_sessions = db.query(ClassSession).filter(
                ClassSession.teacher_id == teacher_id,
                # Filter by period (năm-tháng từ session_date)
            ).count()
            
            # Lấy số buổi hoàn tất
            completed_sessions = db.query(ClassSession).filter(
                ClassSession.teacher_id == teacher_id,
                ClassSession.status == SessionStatus.COMPLETED
            ).count()
            
            # Tính tỉ lệ
            if scheduled_sessions > 0:
                score = Decimal(completed_sessions) / Decimal(scheduled_sessions) * 100
            else:
                score = Decimal(100)  # Nếu không có buổi nào lên lịch, cho điểm full
            
            return min(score, Decimal(100))  # Cap at 100
        
        elif criteria_code == "LESSON_COMPLETION":
            # Tính tỉ lệ hoàn thành nội dung tiết học
            # Có thể dựa trên materials uploaded, homework assigned, etc.
            # Mô phỏng: 85 điểm
            return Decimal(85)
        
        elif criteria_code == "STUDENT_SATISFACTION":
            # Tính từ đánh giá học viên (nếu có)
            # Mô phỏng: 90 điểm
            return Decimal(90)
        
        else:
            # Trường hợp mặc định: 80 điểm
            return Decimal(80)