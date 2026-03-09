from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import json
from pydantic import ValidationError

from app.core.database import get_db
from app.dependencies import get_current_user, CommonQueryParams
from app.models.user import UserRole
from app.models.file_upload import UploadType, AccessLevel

from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException # Đã cập nhật path core.exceptions

from app.schemas.test.test_create import TestCreate, TestUpdate
from app.schemas.test.test_read import (
    TeacherTestListResponse,
    StudentTestListResponse,
    TestDetailResponse,
    TeacherTestDetailResponse,
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

from app.schemas.test.speaking import (
    PreUploadResponse,
    BatchSubmitSpeakingRequest,
    BatchSubmitSpeakingResponse
)
from app.services.test.speaking_service import speaking_service
from app.services.cloudinary import upload_and_save_metadata

router = APIRouter(tags=["Tests"], prefix="/tests", route_class=ResponseWrapperRoute)

# ============================================================
# LIST TESTS
# ============================================================
@router.get("", response_model=PaginationResponse[TeacherTestListResponse])
def list_tests(
    params: CommonQueryParams = Depends(),
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
        raise APIException(status_code=403, code="FORBIDDEN", message="Not authorized")

    return test_service.list_tests(
        db=db,
        skip=params.skip,
        limit=params.limit,
        class_id=class_id,
        status=status,
        skill=skill
    )

@router.get("/student", response_model=PaginationResponse[StudentTestListResponse])
def list_tests_student(
    params: CommonQueryParams = Depends(),
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
        skip=params.skip,
        limit=params.limit
    )

# ============================================================
# CREATE / UPDATE / DELETE / PUBLISH
# ============================================================
@router.post("/create", response_model=ApiResponse[TeacherTestDetailResponse])
async def create_test(
    test_data_str: str = Form(..., description="JSON string of TestCreate schema"),
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (UserRole.TEACHER, UserRole.CENTER_ADMIN):
        raise APIException(status_code=403, code="FORBIDDEN", message="Not authorized")
    
    try:
        test_data_dict = json.loads(test_data_str)
        data = TestCreate(**test_data_dict)
    except (json.JSONDecodeError, ValidationError) as e:
        raise APIException(status_code=422, code="VALIDATION_ERROR", message=f"Invalid test data format: {str(e)}")

    test = await test_service.create_test(
        db=db,
        data=data,
        files=files,
        created_by=current_user.id
    )
    return ApiResponse(data=test_service.get_test_for_teacher(db, test.id))

@router.patch("/{test_id}", response_model=ApiResponse[TeacherTestDetailResponse])
async def update_test(
    test_id: UUID,
    test_data_str: str = Form(...),
    files: list[UploadFile] | None = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (UserRole.TEACHER, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        raise APIException(status_code=403, code="FORBIDDEN", message="Not authorized")

    try:
        payload_dict = json.loads(test_data_str)
        payload = TestUpdate(**payload_dict)
    except Exception as e:
        raise APIException(status_code=400, code="BAD_REQUEST", message=f"Invalid test data: {e}")

    updated_test = await test_service.update_test(
        db=db,
        test_id=test_id,
        payload=payload,
        user_id=current_user.id,
        files=files
    )
    return ApiResponse(data=test_service.get_test_for_teacher(db, updated_test.id))

@router.post("/{test_id}/publish", response_model=ApiResponse[TeacherTestDetailResponse])
def publish_test(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (UserRole.TEACHER, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        raise APIException(status_code=403, code="FORBIDDEN", message="Not authorized")

    published_test = test_service.publish_test(db=db, test_id=test_id, user_id=current_user.id)
    return ApiResponse(data=test_service.get_test_for_teacher(db, published_test.id))

@router.delete("/{test_id}", response_model=ApiResponse[bool])
def delete_test(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (UserRole.TEACHER, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        raise APIException(status_code=403, code="FORBIDDEN", message="Not authorized")

    result = test_service.delete_test(db, test_id, current_user.id)
    return ApiResponse(data=result)

# ============================================================
# STUDENT VIEW & ATTEMPTS
# ============================================================
@router.get("/{test_id}", response_model=ApiResponse[TestDetailResponse])
def get_test_student(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    data = test_service.get_test_for_student(db, test_id)
    return ApiResponse(data=data)

@router.get("/admin/{test_id}", response_model=ApiResponse[TeacherTestDetailResponse])
def get_test_teacher(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (UserRole.TEACHER, UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        raise APIException(status_code=403, code="FORBIDDEN", message="Not authorized")

    data = test_service.get_test_for_teacher(db, test_id)
    return ApiResponse(data=data)

@router.post("/{test_id}/start", response_model=ApiResponse[StartAttemptResponse])
def start_test_attempt(
    test_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return ApiResponse(data=attempt_service.start_attempt(db=db, test_id=test_id, student_id=current_user.id))

@router.post("/attempts/{attempt_id}/submit", response_model=ApiResponse[SubmitAttemptResponse])
async def submit_test_attempt(
    attempt_id: UUID,
    payload: SubmitAttemptRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = await attempt_service.submit_attempt(db=db, attempt_id=attempt_id, data=payload, user_id=current_user.id)
    return ApiResponse(data=result)

# ============================================================
# SPEAKING PROCESS
# ============================================================
@router.post("/attempts/{attempt_id}/speaking/upload/{question_id}", response_model=ApiResponse[PreUploadResponse])
async def pre_upload_speaking_audio(
    attempt_id: UUID,
    question_id: UUID,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    try:
        file_meta = await upload_and_save_metadata(
            db=db,
            uploaded_file=audio,
            user_id=current_user.id,
            upload_type_value=UploadType.AUDIO.value,
            access_level_value=AccessLevel.PRIVATE.value
        )
    except Exception as e:
        raise APIException(status_code=500, code="UPLOAD_FAILED", message=f"Failed to upload file: {str(e)}")
    
    result = await speaking_service.pre_upload_audio(
        db=db, attempt_id=attempt_id, question_id=question_id, file_meta=file_meta, user_id=current_user.id
    )
    return ApiResponse(data=result)

@router.post("/attempts/{attempt_id}/speaking/batch-submit", response_model=ApiResponse[BatchSubmitSpeakingResponse])
async def batch_submit_speaking(
    attempt_id: UUID,
    request: BatchSubmitSpeakingRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    result = await speaking_service.batch_submit_speaking(db=db, attempt_id=attempt_id, request=request, user_id=current_user.id)
    return ApiResponse(data=result)

@router.get("/{test_id}/attempts", response_model=PaginationResponse[TestAttemptSummaryResponse])
def list_test_attempts_for_teacher(
    test_id: UUID,
    params: CommonQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (UserRole.TEACHER, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN):
        raise APIException(status_code=403, code="FORBIDDEN", message="Not authorized")

    return attempt_service.list_attempts_for_teacher(
        db=db,
        test_id=test_id,
        user_id=current_user.id,
        user_role=current_user.role,
        skip=params.skip,
        limit=params.limit
    )

# ============================================================
# ATTEMPT DETAIL & GRADING
# ============================================================
@router.get("/attempts/{attempt_id}", response_model=ApiResponse[TestAttemptDetailResponse])
def get_attempt_detail(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return ApiResponse(data=attempt_service.get_attempt_detail(db=db, attempt_id=attempt_id, user_id=current_user.id))

@router.get("/attempts/{attempt_id}/teacher", response_model=ApiResponse[TestAttemptDetailResponse])
def teacher_view_attempt(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (UserRole.TEACHER, UserRole.CENTER_ADMIN):
        raise APIException(status_code=403, code="FORBIDDEN", message="Not authorized")

    return ApiResponse(data=attempt_service.get_attempt_detail_for_teacher(db=db, attempt_id=attempt_id))

@router.post("/attempts/{attempt_id}/grade", response_model=ApiResponse[TestAttemptDetailResponse])
async def grade_attempt(
    attempt_id: UUID,
    payload: GradeAttemptRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.role not in (UserRole.TEACHER, UserRole.CENTER_ADMIN):
        raise APIException(status_code=403, code="FORBIDDEN", message="Not authorized")

    result = await attempt_service.grade_attempt(
        db=db, attempt_id=attempt_id, teacher_id=current_user.id, data=payload
    )
    return ApiResponse(data=result)