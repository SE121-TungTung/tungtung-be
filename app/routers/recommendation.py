from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from app.core.database import get_db
from app.dependencies import get_current_active_user, get_current_admin_user, CommonQueryParams
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.models.user import User, UserStatus, UserRole
from app.services.recommendation_service import recommendation_service
from app.models.recommendation import RecommendationLog
from sqlalchemy import desc

router = APIRouter(tags=["Recommendations"], prefix="/recommendations", route_class=ResponseWrapperRoute)

@router.get("/today", response_model=ApiResponse[dict])
async def get_today(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Student xem recommendation hôm nay"""
    result = await recommendation_service.get_today(db, current_user.id)
    return ApiResponse(data=result.get("data", {}))

@router.get("/learning-path", response_model=ApiResponse[dict])
async def get_learning_path(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Student xem learning path"""
    log = db.query(RecommendationLog).filter(
        RecommendationLog.student_id == current_user.id
    ).order_by(desc(RecommendationLog.generated_at)).first()
    
    path = log.learning_path if log else {}
    return ApiResponse(data=path)

@router.get("/history", response_model=ApiResponse[list])
async def get_history(params: CommonQueryParams = Depends(), db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Student xem lịch sử recommendation"""
    query = db.query(RecommendationLog).filter(
        RecommendationLog.student_id == current_user.id
    ).order_by(desc(RecommendationLog.generated_at))
    
    total = query.count()
    logs = query.offset((params.page - 1) * params.size).limit(params.size).all()
    
    result = []
    for log in logs:
        result.append({
            "id": str(log.id),
            "generated_at": log.generated_at.isoformat() if log.generated_at else None,
            "recommendation_type": log.recommendation_type,
            "is_read": log.is_read,
            "predicted_band": float(log.predicted_band) if log.predicted_band is not None else None,
            "target_band": float(log.target_band) if log.target_band is not None else None,
            "attendance_rate": float(log.attendance_rate) if log.attendance_rate is not None else None,
            "skill_scores": log.skill_scores
        })
    return ApiResponse(data=result)

@router.post("/generate", response_model=ApiResponse[dict])
async def generate(student_id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    """Admin manual trigger cho 1 student"""
    log = await recommendation_service.generate_recommendation(db, student_id)
    return ApiResponse(data={"id": str(log.id), "status": "generated"})

@router.post("/generate-batch", response_model=ApiResponse[dict])
async def generate_batch(db: Session = Depends(get_db), current_user: User = Depends(get_current_admin_user)):
    """Cron batch trigger cho tất cả active students — parallel processing"""
    # Fetch all active students
    students = db.query(User.id).filter(
        User.status == UserStatus.ACTIVE,
        User.role == UserRole.STUDENT
    ).all()
    
    student_ids = [s[0] for s in students]
    result = await recommendation_service.generate_batch(db, student_ids)
    return ApiResponse(data=result)

@router.patch("/{id}/read", response_model=ApiResponse[dict])
def mark_read(id: UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """Đánh dấu đã đọc"""
    log = db.query(RecommendationLog).filter(
        RecommendationLog.id == id,
        RecommendationLog.student_id == current_user.id
    ).first()
    
    if log:
        log.is_read = True
        db.commit()
        return ApiResponse(data={"id": str(id), "is_read": True})
    return ApiResponse(data={"error": "Not found"})
