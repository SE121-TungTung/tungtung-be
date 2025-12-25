from fastapi import APIRouter
from fastapi import Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies import get_current_admin_user
from app.schemas.test.test_create import TestCreate
from app.schemas.test.test_read import TestResponse, TestTeacherResponse, TestListResponse, TestAttemptDetailResponse
from app.dependencies import get_current_user
from uuid import UUID
from app.models.user import UserRole
from typing import List, Optional
from app.models.test import TestAttempt
from app.schemas.test.test_attempt import (
    StartAttemptResponse,
    SubmitAttemptRequest,
    SubmitAttemptResponse
)

from fastapi import HTTPException, UploadFile, File, Form

from app.services.test.test import test_service
from app.services.test.test_attempt_service import attempt_service

router = APIRouter(tags=["Tests"], prefix="/tests")

@router.get("/", response_model=List[TestListResponse])
def list_tests(
    skip: int = 0,
    limit: int = 20,
    class_id: Optional[UUID] = None,
    status: Optional[str] = None,
    skill: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all available tests
    Nếu bài test tổng hợp nhiều skill, logic này lấy skill đầu tiên
    """
    return test_service.list_tests(db, skip, limit, class_id, status, skill=skill)

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


@router.post("/attempts/{attempt_id}/submit", response_model=SubmitAttemptResponse)
def submit_test_attempt(
    attempt_id: UUID,
    payload: SubmitAttemptRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
    ):
    """
    Submit full attempt. Body must include attempt_id and list of responses.
    """
    attempt = db.query(TestAttempt).filter(TestAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    
    if attempt.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your attempt")

    return attempt_service.submit_attempt(db, payload, attempt_id)

@router.post("/attempts/{attempt_id}/speaking")
async def submit_speaking_answer(
    attempt_id: UUID,
    question_id: UUID = Form(...),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return await attempt_service.submit_speaking(
        db=db,
        attempt_id=attempt_id,
        question_id=question_id,
        audio_file=audio,
        student_id=current_user.id
    )

@router.get("/attempts/{attempt_id}", response_model=TestAttemptDetailResponse)
def get_attempt_detail(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return attempt_service.get_attempt_detail(db, attempt_id, current_user.id)