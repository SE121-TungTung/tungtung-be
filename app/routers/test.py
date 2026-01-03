from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.dependencies import get_current_user
from app.models.user import UserRole

import json
from pydantic import ValidationError

from app.schemas.test.test_create import TestCreate, TestUpdate
from app.schemas.test.test_read import (
    TestResponse,
    TestTeacherResponse,
    TestListResponse,
    TestAttemptDetailResponse
)
from app.schemas.test.test_attempt import (
    StartAttemptResponse,
    SubmitAttemptRequest,
    SubmitAttemptResponse,
    TestAttemptSummaryResponse,
    GradeAttemptRequest
)

from app.services.test.test import test_service
from app.services.test.test_attempt_service import attempt_service

router = APIRouter(tags=["Tests"], prefix="/tests")

# ============================================================
# LIST TESTS
# ============================================================
@router.get("/")
def list_tests(
    skip: int = 0,
    limit: int = 20,
    class_id: Optional[UUID] = None,
    status: Optional[str] = None,
    skill: Optional[str] = None,
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

    return test_service.list_tests(
        db=db,
        skip=skip,
        limit=limit,
        class_id=class_id,
        status=status,
        skill=skill
    )

@router.get("/student")
def list_tests(
    skip: int = 0,
    limit: int = 20,
    class_id: Optional[UUID] = None,
    skill: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return test_service.list_tests_for_student(
        db=db,
        student_id=current_user.id,
        class_id=class_id,
        skill=skill,
        skip=skip,
        limit=limit
    )

# ============================================================
# CREATE TEST (ADMIN)
# ============================================================
@router.post("/create", response_model=TestTeacherResponse)
async def create_test(
    # Nhận JSON string và parse thủ công
    test_data_str: str = Form(..., description="JSON string of TestCreate schema"),
    # Nhận list files (optional)
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (
        UserRole.TEACHER,
        UserRole.CENTER_ADMIN
    ):
        raise HTTPException(status_code=403, detail="Not authorized")
    try:
        # 1. Parse JSON string thành Dict
        test_data_dict = json.loads(test_data_str)
        # 2. Validate bằng Pydantic
        data = TestCreate(**test_data_dict)
    except (json.JSONDecodeError, ValidationError) as e:
        raise HTTPException(status_code=422, detail=f"Invalid test data format: {str(e)}")

    # 3. Gọi Service
    test = await test_service.create_test(
        db=db,
        data=data,
        files=files, # Truyền thêm files
        created_by=current_user.id
    )
    
    return test_service.get_test_for_teacher(db, test.id)

@router.patch("/{test_id}", response_model=TestTeacherResponse)
def update_test(
    test_id: UUID,
    payload: TestUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (
        UserRole.TEACHER,
        UserRole.CENTER_ADMIN,
        UserRole.SYSTEM_ADMIN,
    ):
        raise HTTPException(status_code=403, detail="Not authorized")

    test = test_service.update_test(
        db=db,
        test_id=test_id,
        payload=payload,
        user_id=current_user.id
    )

    return test_service.get_test_for_teacher(db, test.id)

@router.delete("/{test_id}")
def delete_test(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Delete test (soft delete):
    - Only for TEACHER / ADMIN
    - Cannot delete test with attempts
    """
    if current_user.role not in (
        UserRole.TEACHER,
        UserRole.CENTER_ADMIN,
        UserRole.SYSTEM_ADMIN,
    ):
        raise HTTPException(status_code=403, detail="Not authorized")

    test_service.delete_test(db, test_id, current_user.id)
    return {"success": True}

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
        data=payload,
        user_id=current_user.id
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
        file=audio,
        user_id=current_user.id
    )

@router.get("/{test_id}/attempts", response_model=list[TestAttemptSummaryResponse])
def list_test_attempts_for_teacher(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (
        UserRole.TEACHER,
        UserRole.CENTER_ADMIN,
        UserRole.SYSTEM_ADMIN,
    ):
        raise HTTPException(403, "Not authorized")

    return attempt_service.list_attempts_for_teacher(
        db=db,
        test_id=test_id,
        teacher_id=current_user.id
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

# Teacher view attempt
@router.get("/attempts/{attempt_id}/teacher")
def teacher_view_attempt(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (
        UserRole.TEACHER,
        UserRole.CENTER_ADMIN
    ):
        raise HTTPException(403, "Not authorized")

    return attempt_service.get_attempt_detail_for_teacher(
        db=db,
        attempt_id=attempt_id
    )


# Teacher grade attempt
@router.post("/attempts/{attempt_id}/grade")
async def grade_attempt(
    attempt_id: UUID,
    payload: GradeAttemptRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (
        UserRole.TEACHER,
        UserRole.CENTER_ADMIN
    ):
        raise HTTPException(403, "Not authorized")

    return await attempt_service.grade_attempt(
        db=db,
        attempt_id=attempt_id,
        teacher_id=current_user.id,
        data=payload
    )

