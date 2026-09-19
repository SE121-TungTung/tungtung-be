"""
Router: /vocabulary
Spec ref: ielts_system_spec_part2.md § 3.2.3 & § 4.2

Endpoints:
  POST   /vocabulary/save         — Lưu từ vào sổ tay (require_non_guest)
  GET    /vocabulary/my-words     — Danh sách từ của tôi (require_non_guest)
  PATCH  /vocabulary/{id}         — Cập nhật mastery_level (require_non_guest)
  DELETE /vocabulary/{id}         — Xoá từ (require_non_guest)
"""
from uuid import UUID
from typing import Optional
from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.route import ResponseWrapperRoute
from app.core.database import get_db
from app.core.exceptions import APIException
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.schemas.vocabulary import (
    VocabularySaveRequest,
    VocabularyUpdateRequest,
    VocabularyResponse,
)
from app.dependencies import require_non_guest
from app.services.vocabulary_service import vocabulary_service

router = APIRouter(
    tags=["Vocabulary"],
    prefix="/vocabulary",
    route_class=ResponseWrapperRoute,
)


# ---------------------------------------------------------------------------
# POST /vocabulary/save
# ---------------------------------------------------------------------------

@router.post("/save", response_model=ApiResponse[VocabularyResponse], status_code=201)
async def save_vocabulary(
    payload: VocabularySaveRequest,
    current_user=Depends(require_non_guest),
    db: Session = Depends(get_db),
):
    """
    **Lưu từ vựng vào sổ tay cá nhân.**

    - Yêu cầu tài khoản thật (không dành cho Guest).
    - `source_passage_id` tuỳ chọn — gắn với bài đọc/nghe nguồn.
    - Trả về 409 nếu từ đó đã được lưu từ cùng 1 passage.
    """
    entry = await vocabulary_service.save_word(
        db=db,
        user_id=current_user.id,
        payload=payload,
    )
    return ApiResponse(
        data=VocabularyResponse.model_validate(entry),
        message="Word saved successfully.",
    )


# ---------------------------------------------------------------------------
# GET /vocabulary/my-words
# ---------------------------------------------------------------------------

@router.get("/my-words", response_model=PaginationResponse[VocabularyResponse])
async def get_my_vocabulary(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    limit: int = Query(20, ge=1, le=100, description="Số từ mỗi trang"),
    mastery_level: Optional[int] = Query(
        None, ge=0, le=3,
        description="Lọc theo mức độ thuộc từ: 0=new, 1=learning, 2=familiar, 3=mastered"
    ),
    word_type: Optional[str] = Query(
        None, max_length=50,
        description="Lọc theo loại từ: noun, verb, adj, adv, phrase..."
    ),
    current_user=Depends(require_non_guest),
    db: Session = Depends(get_db),
):
    """
    **Lấy danh sách từ vựng cá nhân (có filter + pagination).**

    Hỗ trợ lọc theo:
    - `mastery_level` — mức độ thuộc từ (0-3)
    - `word_type` — loại từ (noun, verb, adj, adv, phrase)
    """
    items, total = await vocabulary_service.get_my_words(
        db=db,
        user_id=current_user.id,
        page=page,
        limit=limit,
        mastery_level=mastery_level,
        word_type=word_type,
    )
    total_pages = ceil(total / limit) if total else 0
    return PaginationResponse(
        data=[VocabularyResponse.model_validate(item) for item in items],
        meta=PaginationMetadata(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        ),
    )


# ---------------------------------------------------------------------------
# PATCH /vocabulary/{id}
# ---------------------------------------------------------------------------

@router.patch("/{vocab_id}", response_model=ApiResponse[VocabularyResponse])
async def update_vocabulary_mastery(
    vocab_id: UUID,
    payload: VocabularyUpdateRequest,
    current_user=Depends(require_non_guest),
    db: Session = Depends(get_db),
):
    """
    **Cập nhật mức độ thuộc từ (mastery_level).**

    - `0` = new, `1` = learning, `2` = familiar, `3` = mastered
    - Chỉ chủ sở hữu mới được cập nhật.
    """
    entry = await vocabulary_service.update_mastery(
        db=db,
        vocab_id=vocab_id,
        user_id=current_user.id,
        payload=payload,
    )
    return ApiResponse(
        data=VocabularyResponse.model_validate(entry),
        message="Mastery level updated.",
    )


# ---------------------------------------------------------------------------
# DELETE /vocabulary/{id}
# ---------------------------------------------------------------------------

@router.delete("/{vocab_id}", response_model=ApiResponse[None])
async def delete_vocabulary(
    vocab_id: UUID,
    current_user=Depends(require_non_guest),
    db: Session = Depends(get_db),
):
    """
    **Xoá từ khỏi sổ tay cá nhân.**

    Chỉ chủ sở hữu mới được xoá. Trả về 404 nếu không tìm thấy.
    """
    await vocabulary_service.delete_word(
        db=db,
        vocab_id=vocab_id,
        user_id=current_user.id,
    )
    return ApiResponse(data=None, message="Word deleted successfully.")
