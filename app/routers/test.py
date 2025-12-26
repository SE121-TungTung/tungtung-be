from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.dependencies import get_current_user, get_current_admin_user
from app.models.user import UserRole

from app.schemas.test.test_create import TestCreate
from app.schemas.test.test_read import (
    TestResponse,
    TestTeacherResponse,
    TestListResponse,
    TestAttemptDetailResponse
)
from app.schemas.test.test_attempt import (
    StartAttemptResponse,
    SubmitAttemptRequest,
    SubmitAttemptResponse
)

from app.services.test.test import test_service
from app.services.test.test_attempt_service import attempt_service

router = APIRouter(tags=["Tests"], prefix="/tests")

# ============================================================
# LIST TESTS
# ============================================================
@router.get("/", response_model=List[TestListResponse])
def list_tests(
    skip: int = 0,
    limit: int = 20,
    class_id: Optional[UUID] = None,
    status: Optional[str] = None,
    skill: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return test_service.list_tests(
        db=db,
        skip=skip,
        limit=limit,
        class_id=class_id,
        status=status,
        skill=skill
    )

# ============================================================
# CREATE TEST (ADMIN)
# ============================================================
@router.post("/create", response_model=TestTeacherResponse)
async def create_test(
    data: TestCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_admin_user)
):
    test = await test_service.create_test(
        db=db,
        data=data,
        created_by=current_user.id
    )
    return test_service.get_test_for_teacher(db, test.id)

# ============================================================
# GET TEST - STUDENT
# ============================================================
@router.get("/{test_id}", response_model=TestResponse)
def get_test_student(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Student view:
    - Only PUBLISHED tests
    - No correct answers
    """
    return test_service.get_test_for_student(db, test_id)

# ============================================================
# GET TEST - TEACHER / ADMIN
# ============================================================
@router.get("/admin/{test_id}", response_model=TestTeacherResponse)
def get_test_teacher(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (
        UserRole.TEACHER,
        UserRole.OFFICE_ADMIN,
        UserRole.CENTER_ADMIN,
        UserRole.SYSTEM_ADMIN,
    ):
        raise HTTPException(status_code=403, detail="Not authorized")

    return test_service.get_test_for_teacher(db, test_id)

# ============================================================
# START ATTEMPT
# ============================================================
@router.post("/{test_id}/start", response_model=StartAttemptResponse)
def start_test_attempt(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Start attempt:
    - Test must be published
    - No active attempt
    - Not exceed max_attempts
    """
    return attempt_service.start_attempt(
        db=db,
        test_id=test_id,
        student_id=current_user.id
    )

# ============================================================
# SUBMIT ATTEMPT
# ============================================================
@router.post("/attempts/{attempt_id}/submit", response_model=SubmitAttemptResponse)
def submit_test_attempt(
    attempt_id: UUID,
    payload: SubmitAttemptRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Submit full attempt:
    - Ownership check
    - Attempt must be IN_PROGRESS
    - Auto grading only where allowed
    """
    return attempt_service.submit_attempt(
        db=db,
        attempt_id=attempt_id,
        payload=payload,
        student_id=current_user.id
    )

# ============================================================
# SUBMIT SPEAKING
# ============================================================
@router.post("/attempts/{attempt_id}/speaking")
async def submit_speaking_answer(
    attempt_id: UUID,
    question_id: UUID = Form(...),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Speaking submit:
    - Validate ownership
    - Validate question type == SPEAKING
    """
    return await attempt_service.submit_speaking(
        db=db,
        attempt_id=attempt_id,
        question_id=question_id,
        audio_file=audio,
        student_id=current_user.id
    )

# ============================================================
# GET ATTEMPT DETAIL
# ============================================================
@router.get("/attempts/{attempt_id}", response_model=TestAttemptDetailResponse)
def get_attempt_detail(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return attempt_service.get_attempt_detail(
        db=db,
        attempt_id=attempt_id,
        student_id=current_user.id
    )
