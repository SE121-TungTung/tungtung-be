"""Router: Adaptive Quiz (CAT & IRT)
Prefix: /api/v1/adaptive-quiz

Endpoints:
  /sessions                        POST  Start new CAT session (Student / Guest)
  /sessions                        GET   List user CAT sessions (Student / Guest)
  /sessions/{id}                   GET   Get session details & theta history (Student owner / Admin)
  /sessions/{id}/next-question     GET   Fetch next adaptive question (Student owner)
  /sessions/{id}/responses         POST  Submit response & recalculate theta (Student owner)
  /sessions/{id}/finish            POST  Finalize session & calculate final band (Student owner)
  /questions                       GET   List questions with IRT parameters (Teacher / Admin)
  /questions/{id}/irt              PUT   Manually update question IRT parameters (Teacher / Admin)
  /calibration-stats               GET   Get overall calibration metrics (Teacher / Admin)
  /calibrate                       POST  Trigger batch calibration job (System Admin)
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.route import ResponseWrapperRoute
from app.dependencies import (
    get_current_active_user,
    require_any_role,
    require_role,
)
from app.models.user import User, UserRole
from app.schemas.adaptive_quiz import (
    AdaptiveSessionResponse,
    CalibrationStatsResponse,
    FinishSessionResponse,
    NextQuestionResponse,
    QuestionIRTRead,
    StartSessionRequest,
    SubmitResponseRequest,
    SubmitResponseResponse,
    TriggerCalibrateRequest,
    TriggerCalibrateResponse,
    UpdateQuestionIRTRequest,
)
from app.schemas.base_schema import PaginationMetadata, PaginationResponse
from app.services.adaptive_quiz_service import AdaptiveQuizService
from app.services.irt_calibration_service import IRTCalibrationService


# RBAC Role Helpers
_require_student_or_guest = require_any_role(
    UserRole.STUDENT, UserRole.GUEST_STUDENT
)
_require_staff_or_admin = require_any_role(
    UserRole.TEACHER, UserRole.TA, UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN
)
_require_system_admin = require_role(UserRole.SYSTEM_ADMIN)


router = APIRouter(
    prefix="/adaptive-quiz",
    tags=["Adaptive Quiz (CAT & IRT)"],
    route_class=ResponseWrapperRoute,
)

quiz_service = AdaptiveQuizService()
calibration_service = IRTCalibrationService()


# ---------------------------------------------------------------------------
# 1. Start CAT Session
# ---------------------------------------------------------------------------
@router.post(
    "/sessions",
    response_model=AdaptiveSessionResponse,
    summary="Start or resume an adaptive test session",
)
def start_session(
    payload: StartSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_student_or_guest),
):
    session = quiz_service.start_session(
        db=db,
        current_user=current_user,
        skill_area=payload.skill_area,
        max_items=payload.max_items or 20,
    )
    return session


# ---------------------------------------------------------------------------
# 2. List user CAT sessions
# ---------------------------------------------------------------------------
@router.get(
    "/sessions",
    summary="List past adaptive test sessions of current user",
)
def list_sessions(
    skill_area: Optional[str] = Query(None, description="Filter by skill area: reading / listening"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_student_or_guest),
):
    items, total = quiz_service.list_user_sessions(
        db=db,
        current_user=current_user,
        skill_area=skill_area,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    return PaginationResponse(
        data=[AdaptiveSessionResponse.model_validate(s) for s in items],
        meta=PaginationMetadata(
            page=page,
            limit=page_size,
            total=total,
            total_pages=total_pages,
        ),
    )


# ---------------------------------------------------------------------------
# 3. Get session details & theta history
# ---------------------------------------------------------------------------
@router.get(
    "/sessions/{id}",
    response_model=AdaptiveSessionResponse,
    summary="Get adaptive session detail with theta progression history",
)
def get_session(
    id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    return quiz_service.get_session(db=db, current_user=current_user, session_id=id)


# ---------------------------------------------------------------------------
# 4. Fetch next adaptive question (Fisher Information max)
# ---------------------------------------------------------------------------
@router.get(
    "/sessions/{id}/next-question",
    response_model=NextQuestionResponse,
    summary="Get next optimal question selected by Fisher Information",
)
def get_next_question(
    id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_student_or_guest),
):
    return quiz_service.get_next_question(db=db, current_user=current_user, session_id=id)


# ---------------------------------------------------------------------------
# 5. Submit response & update theta
# ---------------------------------------------------------------------------
@router.post(
    "/sessions/{id}/responses",
    response_model=SubmitResponseResponse,
    summary="Submit answer and update latent ability theta via MLE/EAP",
)
def submit_response(
    id: UUID,
    payload: SubmitResponseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_student_or_guest),
):
    return quiz_service.submit_response(
        db=db,
        current_user=current_user,
        session_id=id,
        question_id=payload.question_id,
        response_data=payload.response_data,
        time_spent_seconds=payload.time_spent_seconds,
    )


# ---------------------------------------------------------------------------
# 6. Finalize session & get report
# ---------------------------------------------------------------------------
@router.post(
    "/sessions/{id}/finish",
    response_model=FinishSessionResponse,
    summary="Finalize adaptive session and return final IELTS Band report",
)
def finish_session(
    id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_student_or_guest),
):
    return quiz_service.finish_session(db=db, current_user=current_user, session_id=id)


# ---------------------------------------------------------------------------
# 7. List questions with IRT parameters (Teacher / Admin)
# ---------------------------------------------------------------------------
@router.get(
    "/questions",
    summary="List questions with psychometric IRT parameters (Staff/Admin)",
)
def list_questions(
    skill_area: Optional[str] = Query(None, description="reading / listening"),
    calibrated: Optional[bool] = Query(None, description="Filter calibrated status"),
    search: Optional[str] = Query(None, description="Search by title or text"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_staff_or_admin),
):
    items, total = calibration_service.list_questions_with_irt(
        db=db,
        skill_area=skill_area,
        calibrated=calibrated,
        search=search,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    return PaginationResponse(
        data=[QuestionIRTRead.model_validate(q) for q in items],
        meta=PaginationMetadata(
            page=page,
            limit=page_size,
            total=total,
            total_pages=total_pages,
        ),
    )


# ---------------------------------------------------------------------------
# 8. Manually update question IRT parameters (Teacher / Admin)
# ---------------------------------------------------------------------------
@router.put(
    "/questions/{id}/irt",
    response_model=QuestionIRTRead,
    summary="Manually update IRT parameters (a, b, c) of a question",
)
def update_question_irt(
    id: UUID,
    payload: UpdateQuestionIRTRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_staff_or_admin),
):
    question = calibration_service.update_question_irt(
        db=db,
        question_id=id,
        a=payload.irt_discrimination,
        b=payload.irt_difficulty,
        c=payload.irt_guessing,
        is_cat_eligible=payload.is_cat_eligible if payload.is_cat_eligible is not None else True,
    )
    return question


# ---------------------------------------------------------------------------
# 9. Get calibration statistics (Teacher / Admin)
# ---------------------------------------------------------------------------
@router.get(
    "/calibration-stats",
    response_model=CalibrationStatsResponse,
    summary="Get calibration health and item pool statistics",
)
def get_calibration_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_staff_or_admin),
):
    return calibration_service.get_calibration_stats(db=db)


# ---------------------------------------------------------------------------
# 10. Trigger batch calibration job (System Admin only)
# ---------------------------------------------------------------------------
@router.post(
    "/calibrate",
    response_model=TriggerCalibrateResponse,
    summary="Trigger empirical batch calibration of question parameters (System Admin)",
)
def trigger_batch_calibrate(
    payload: Optional[TriggerCalibrateRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(_require_system_admin),
):
    min_resp = payload.min_responses if payload else 50
    return calibration_service.trigger_batch_calibration(db=db, min_responses=min_resp)
