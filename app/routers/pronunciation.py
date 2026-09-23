from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, File, UploadFile, Form, Path, status
from sqlalchemy.orm import Session

from app.core.route import ResponseWrapperRoute
from app.core.database import get_db
from app.dependencies import get_current_active_user
from app.models.user import User
from app.models.pronunciation import TargetType
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.schemas.pronunciation import (
    PronunciationPracticeCreateResponse,
    PronunciationPracticeDetailResponse,
    PronunciationPracticeListItem,
    PronunciationStatsResponse,
    PronunciationStreakResponse,
)
from app.services.pronunciation_service import pronunciation_service

router = APIRouter(
    prefix="/pronunciation",
    tags=["Pronunciation Practice"],
    route_class=ResponseWrapperRoute,
)


@router.post(
    "/practices",
    response_model=ApiResponse[PronunciationPracticeCreateResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Chấm điểm và lưu bài luyện phát âm",
    description="Nhận file ghi âm, gửi AI phân tích 7 thành phần, lưu kết quả và audio.",
)
async def create_practice(
    audio: UploadFile = File(..., description="File âm thanh giọng đọc (wav, mp3, m4a, webm)"),
    target: str = Form(..., description="Từ, cụm từ, câu hoặc âm IPA mẫu"),
    target_type: TargetType = Form(TargetType.WORD, description="Loại mục tiêu: word, phrase, sentence, ipa"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    audio_bytes = await audio.read()
    practice = await pronunciation_service.grade_and_save_practice(
        db=db,
        student=current_user,
        audio_filename=audio.filename or "practice.wav",
        audio_bytes=audio_bytes,
        audio_content_type=audio.content_type or "audio/wav",
        target=target,
        target_type=target_type,
    )
    return ApiResponse(
        data=PronunciationPracticeCreateResponse.model_validate(practice),
        message="Chấm điểm phát âm thành công.",
    )


@router.get(
    "/practices/stats",
    response_model=ApiResponse[PronunciationStatsResponse],
    summary="Thống kê tổng hợp kết quả luyện phát âm",
    description="Trả về tổng số lượt luyện tập, điểm trung bình, phân bổ theo target_type, danh sách âm yếu và xu hướng gần đây.",
)
async def get_practice_stats(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    stats = pronunciation_service.get_student_stats(db=db, student_id=current_user.id)
    return ApiResponse(
        data=PronunciationStatsResponse.model_validate(stats),
    )


@router.get(
    "/practices/streak",
    response_model=ApiResponse[PronunciationStreakResponse],
    summary="Thông tin chuỗi ngày luyện tập liên tục (Streak)",
    description="Tính toán current streak, longest streak, ngày luyện gần nhất và số ngày active trong tháng.",
)
async def get_practice_streak(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    streak = pronunciation_service.get_student_streak(db=db, student_id=current_user.id)
    return ApiResponse(
        data=PronunciationStreakResponse.model_validate(streak),
    )


@router.get(
    "/practices",
    response_model=PaginationResponse[PronunciationPracticeListItem],
    summary="Lịch sử luyện phát âm cá nhân có phân trang",
    description="Lấy danh sách các bài luyện tập của học viên, hỗ trợ lọc theo target_type.",
)
async def list_practices(
    page: int = Query(1, ge=1, description="Số trang (từ 1)"),
    limit: int = Query(20, ge=1, le=100, description="Số bản ghi mỗi trang"),
    target_type: Optional[TargetType] = Query(None, description="Lọc theo target_type (word, phrase, sentence, ipa)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    result = pronunciation_service.get_student_history(
        db=db,
        student_id=current_user.id,
        target_type=target_type,
        page=page,
        limit=limit,
    )
    items = [PronunciationPracticeListItem.model_validate(item) for item in result["items"]]
    meta = PaginationMetadata(**result["meta"])
    return PaginationResponse(
        data=items,
        meta=meta,
    )


@router.get(
    "/practices/{id}",
    response_model=ApiResponse[PronunciationPracticeDetailResponse],
    summary="Chi tiết lượt luyện phát âm theo ID",
    description="Xem toàn bộ kết quả phân tích 7 thành phần, chi tiết từng âm vị phoneme, và nhận xét.",
)
async def get_practice_detail(
    id: UUID = Path(..., description="ID của lượt luyện tập"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    practice = pronunciation_service.get_practice_detail(
        db=db,
        practice_id=id,
        current_user=current_user,
    )
    return ApiResponse(
        data=PronunciationPracticeDetailResponse.model_validate(practice),
    )
