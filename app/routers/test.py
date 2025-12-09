from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies import get_current_admin_user
from app.schemas.test_create import TestCreate
from app.schemas.test_read import TestResponse, TestTeacherResponse
from app.dependencies import get_current_user
from uuid import UUID
from app.models.user import UserRole
from app.schemas.test_attempt import (
    StartAttemptResponse,
    SubmitAttemptRequest,
    SubmitAttemptResponse
)

from fastapi import HTTPException

from app.services.test import test_service
from app.services.test_attempt_service import attempt_service

router = APIRouter(tags=["Tests"], prefix="/tests")

@router.post("/create")
async def create_test(
    data: TestCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    return await test_service.create_test(db, data, created_by=current_user.id)

@router.get("/{test_id}", response_model=TestResponse)
def get_test_student(test_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Student view (or public view).
    - Returns the student-safe representation of the test (no correct_answer).
    - Optionally perform access checks (class enrollment).
    """
    # Optional: check enrollment/permission
    # if test is tied to a class, ensure current_user is enrolled (implement your own function)
    # ensure only students or teachers allowed; 
    return test_service.get_test_for_student(db, test_id)


@router.get("/admin/{test_id}", response_model=TestTeacherResponse)
def get_test_teacher(test_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Teacher/Admin view: must be teacher/admin.
    """
    # permission check
    if current_user.role not in (UserRole.TEACHER, UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        raise HTTPException(status_code=403, detail="Not authorized")
    return test_service.get_test_for_teacher(db, test_id)


@router.post("/{test_id}/start", response_model=StartAttemptResponse)
def start_test_attempt(test_id: UUID, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Start an attempt for current_user on test_id.
    Returns attempt_id and started_at.
    """
    return attempt_service.start_attempt(db, test_id, current_user.id)


@router.post("/{attempt_id}/submit", response_model=SubmitAttemptResponse)
def submit_test_attempt(attempt_id: UUID, payload: SubmitAttemptRequest, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """
    Submit full attempt. Body must include attempt_id and list of responses.
    """
    # small validation: attempt_id belongs to the test_id
    # (service will check again but quick fail fast)
    # attempt = db.query(TestAttempt).filter(TestAttempt.id==payload.attempt_id).first()
    # if attempt and attempt.test_id != test_id: raise HTTPException(400)

    return attempt_service.submit_attempt(db, payload, attempt_id)