from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
import json

from app.core.database import get_db
from app.models.academic import Course, Class, CourseStatus, ClassStatus
from app.models.lead import Lead, LeadStatus
from app.models.user import User, UserRole, UserStatus
from app.schemas.public import PublicCourseResponse, PublicClassResponse, PublicLeadCreate
from app.schemas.base_schema import ApiResponse
from app.schemas.notification import NotificationCreate
from app.models.notification import NotificationType, NotificationPriority
from app.services.notification_service import notification_service
from app.core.redis import redis_manager
from app.services.chatbot_service import chatbot_service
from app.dependencies import get_current_user_optional


class PublicChatRequest(BaseModel):
    message: str
    history: list = []
    retrieval_mode: str = "hybrid_rerank"


router = APIRouter(prefix="/public", tags=["Public"])


@router.get("/courses", response_model=ApiResponse[List[PublicCourseResponse]])
def get_public_courses(db: Session = Depends(get_db)):
    courses = db.query(Course).filter(Course.status == CourseStatus.ACTIVE).all()

    data = []
    for c in courses:
        data.append(PublicCourseResponse(
            id=c.id,
            name=c.name,
            description=c.description,
            level=c.level.value if hasattr(c.level, 'value') else c.level,
            course_type=c.course_type.value if hasattr(c.course_type, 'value') else c.course_type,
            duration_hours=c.duration_hours,
            fee_amount=float(c.fee_amount),
            currency=c.currency
        ))

    return ApiResponse(data=data)


@router.get("/classes/open", response_model=ApiResponse[List[PublicClassResponse]])
def get_public_open_classes(db: Session = Depends(get_db)):
    classes = (
        db.query(Class)
        .join(Course, Class.course_id == Course.id)
        .filter(Class.status == ClassStatus.OPEN)
        .filter(Course.status == CourseStatus.ACTIVE)
        .all()
    )

    data = []
    for cls in classes:
        available = max(0, cls.max_students - cls.current_students)
        data.append(PublicClassResponse(
            id=cls.id,
            name=cls.name,
            course_id=cls.course_id,
            course_name=cls.course.name,
            course_level=cls.course.level.value if hasattr(cls.course.level, 'value') else cls.course.level,
            start_date=cls.start_date,
            end_date=cls.end_date,
            sessions_per_week=cls.sessions_per_week,
            is_online=cls.is_online,
            fee_amount=float(cls.fee_amount),
            max_students=cls.max_students,
            current_students=cls.current_students,
            available_spots=available
        ))

    return ApiResponse(data=data)


@router.post("/leads", response_model=ApiResponse[dict])
def create_public_lead(payload: PublicLeadCreate, db: Session = Depends(get_db)):
    new_lead = Lead(
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        target_band=payload.target_band,
        notes=payload.intent,
        source="homepage_form",
        status=LeadStatus.NEW
    )
    db.add(new_lead)
    db.commit()
    db.refresh(new_lead)

    admins = db.query(User).filter(
        User.role.in_([UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN]),
        User.status == UserStatus.ACTIVE
    ).all()

    for admin in admins:
        noti = NotificationCreate(
            user_id=admin.id,
            title="Có khách hàng mới đăng ký tư vấn",
            content=f"Khách hàng {new_lead.full_name} ({new_lead.phone}) vừa để lại thông tin tư vấn.",
            priority=NotificationPriority.NORMAL,
            notification_type=NotificationType.SYSTEM_ALERT,
            channels=["in_app"],
            action_url="/admin/leads"
        )
        notification_service.send_notification_sync(db, noti)

    return ApiResponse(message="Đăng ký nhận tư vấn thành công", data={"id": new_lead.id})


async def _check_and_increment_public_quota(request: Request, current_user: User | None):
    ip_address = request.client.host if request.client else "unknown"

    if current_user and current_user.role == UserRole.GUEST:
        quota_key = f"chatbot_quota:user:{current_user.id}"
        limit = 10
        role_label = "guest_student"
    elif current_user:
        quota_key = None
        limit = None
        role_label = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    else:
        quota_key = f"chatbot_quota:ip:{ip_address}"
        limit = 5
        role_label = "guest"

    if quota_key and redis_manager.redis_client:
        current_count = await redis_manager.redis_client.get(quota_key)
        if current_count and int(current_count) >= limit:
            raise HTTPException(status_code=429, detail="QUOTA_EXCEEDED")

        pipe = redis_manager.redis_client.pipeline()
        pipe.incr(quota_key)
        if not current_count:
            pipe.expire(quota_key, 86400)
        await pipe.execute()

    return quota_key, role_label


@router.post("/chatbot/ask", response_model=ApiResponse[dict])
async def public_chat_with_ai(
    request: Request,
    payload: PublicChatRequest,
    current_user: User | None = Depends(get_current_user_optional)
):
    quota_key, role_label = await _check_and_increment_public_quota(request, current_user)

    try:
        response = await chatbot_service.ask_bot(
            message=payload.message,
            user_role=role_label,
            history=payload.history,
            retrieval_mode=payload.retrieval_mode,
        )
        return ApiResponse(data=response)
    except Exception as e:
        if quota_key and redis_manager.redis_client:
            await redis_manager.redis_client.decr(quota_key)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chatbot/ask/stream")
async def public_chat_with_ai_stream(
    request: Request,
    payload: PublicChatRequest,
    current_user: User | None = Depends(get_current_user_optional)
):
    quota_key, role_label = await _check_and_increment_public_quota(request, current_user)

    try:
        stream_gen = await chatbot_service.ask_bot_stream(
            message=payload.message,
            user_role=role_label,
            history=payload.history,
            retrieval_mode=payload.retrieval_mode,
        )

        async def sse_wrapper():
            async for chunk in stream_gen:
                if isinstance(chunk, dict):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'text': str(chunk)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(sse_wrapper(), media_type="text/event-stream")
    except Exception as e:
        if quota_key and redis_manager.redis_client:
            await redis_manager.redis_client.decr(quota_key)
        raise HTTPException(status_code=500, detail=str(e))
