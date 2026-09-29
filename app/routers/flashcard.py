"""
Router: Flashcard
Prefix: /api/v1

Endpoints:
  /flashcard-decks                      GET  list, POST create
  /flashcard-decks/{id}                 GET  detail, PUT update, DELETE soft-delete
  /flashcard-decks/{id}/cards           GET  list cards, POST create card
  /flashcard-decks/{id}/cards/{cid}     PUT  update card, DELETE soft-delete card
  /flashcards/due                       GET  due cards for today
  /flashcards/reviews                   POST submit rating
  /flashcards/stats                     GET  personal stats
  /flashcards/import-from-vocabulary    POST import từ user_vocabulary
"""
from uuid import UUID
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.route import ResponseWrapperRoute
from app.core.database import get_db
from app.dependencies import (
    get_current_active_user,
    require_any_role,
    get_current_teacher_ta_or_admin,
)
from app.models.user import UserRole
from app.models.flashcard import TopicTag, DeckLevel
from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.schemas.flashcard import (
    FlashcardDeckCreate, FlashcardDeckUpdate, FlashcardDeckResponse,
    FlashcardCreate, FlashcardUpdate, FlashcardResponse, FlashcardWithReviewResponse,
    ReviewSubmitRequest, ReviewResponse,
    FlashcardStatsResponse, DailyActivity,
    ImportFromVocabularyRequest,
)
from app.services.flashcard_service import (
    flashcard_deck_service,
    flashcard_card_service,
    flashcard_review_service,
    flashcard_stats_service,
)
from app.repositories.flashcard import flashcard_review_repo

# ---- RBAC helpers ----
_require_content_manager = require_any_role(
    UserRole.TEACHER, UserRole.TA, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN
)
_require_student = require_any_role(
    UserRole.STUDENT, UserRole.GUEST_STUDENT
)

router = APIRouter(
    tags=["Flashcard"],
    route_class=ResponseWrapperRoute,
)


# ============================================================
# /flashcard-decks  (5 endpoints)
# ============================================================

@router.get(
    "/flashcard-decks",
    response_model=PaginationResponse[FlashcardDeckResponse],
    summary="Danh sách flashcard decks",
)
async def list_decks(
    topic_tag: Optional[str] = Query(None, description="Filter theo topic: ielts, toeic, general, business, academic, other"),
    level: Optional[str] = Query(None, description="Filter theo level: beginner, intermediate, advanced, expert"),
    is_public: Optional[bool] = Query(None, description="true=chỉ public, false=chỉ private"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    **Lấy danh sách Flashcard Decks.**

    - Trả về tất cả deck public + deck do user hiện tại tạo.
    - Hỗ trợ filter theo `topic_tag`, `level`, `is_public`.
    - Kèm theo `due_today_count` cho mỗi deck.
    """
    # Parse enum filters
    topic_enum = None
    if topic_tag:
        try:
            topic_enum = TopicTag(topic_tag)
        except ValueError:
            topic_enum = None

    level_enum = None
    if level:
        try:
            level_enum = DeckLevel(level)
        except ValueError:
            level_enum = None

    decks, total = await flashcard_deck_service.get_list(
        db, user_id=current_user.id,
        topic_tag=topic_enum, level=level_enum,
        is_public=is_public, page=page, limit=limit,
    )

    items = []
    for deck in decks:
        resp = FlashcardDeckResponse.model_validate(deck)
        resp.due_today_count = flashcard_review_repo.get_due_count_for_deck(
            db, user_id=current_user.id, deck_id=deck.id
        )
        items.append(resp)

    total_pages = ceil(total / limit) if total else 0
    return PaginationResponse(
        data=items,
        meta=PaginationMetadata(page=page, limit=limit, total=total, total_pages=total_pages),
    )


@router.post(
    "/flashcard-decks",
    response_model=ApiResponse[FlashcardDeckResponse],
    status_code=201,
    summary="Tạo flashcard deck mới",
)
async def create_deck(
    payload: FlashcardDeckCreate,
    current_user=Depends(_require_content_manager),
    db: Session = Depends(get_db),
):
    """
    **Tạo deck thẻ học mới.**

    - Chỉ TEACHER, TA, CENTER_ADMIN, SYSTEM_ADMIN mới có quyền tạo.
    - `guest_student` hoặc `student` sẽ nhận HTTP 403.
    """
    deck = await flashcard_deck_service.create_deck(db, user_id=current_user.id, payload=payload)
    return ApiResponse(data=FlashcardDeckResponse.model_validate(deck), message="Deck created successfully.")


@router.get(
    "/flashcard-decks/{deck_id}",
    response_model=ApiResponse[FlashcardDeckResponse],
    summary="Chi tiết một flashcard deck",
)
async def get_deck_detail(
    deck_id: UUID,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """**Lấy chi tiết một Flashcard Deck theo ID.**"""
    deck = await flashcard_deck_service.get_detail(db, deck_id)
    resp = FlashcardDeckResponse.model_validate(deck)
    resp.due_today_count = flashcard_review_repo.get_due_count_for_deck(
        db, user_id=current_user.id, deck_id=deck.id
    )
    return ApiResponse(data=resp)


@router.put(
    "/flashcard-decks/{deck_id}",
    response_model=ApiResponse[FlashcardDeckResponse],
    summary="Cập nhật flashcard deck",
)
async def update_deck(
    deck_id: UUID,
    payload: FlashcardDeckUpdate,
    current_user=Depends(_require_content_manager),
    db: Session = Depends(get_db),
):
    """
    **Cập nhật thông tin Flashcard Deck.**

    - Chỉ người tạo deck mới được sửa.
    - TEACHER, TA, CENTER_ADMIN, SYSTEM_ADMIN.
    """
    deck = await flashcard_deck_service.update_deck(db, deck_id=deck_id, user_id=current_user.id, payload=payload)
    return ApiResponse(data=FlashcardDeckResponse.model_validate(deck), message="Deck updated successfully.")


@router.delete(
    "/flashcard-decks/{deck_id}",
    response_model=ApiResponse[None],
    summary="Xóa mềm flashcard deck",
)
async def delete_deck(
    deck_id: UUID,
    current_user=Depends(_require_content_manager),
    db: Session = Depends(get_db),
):
    """
    **Xóa mềm (soft delete) một Flashcard Deck.**

    - Chỉ người tạo deck mới được xóa.
    - Deck không bị xóa vĩnh viễn, chỉ đánh dấu `deleted_at`.
    """
    await flashcard_deck_service.soft_delete_deck(db, deck_id=deck_id, user_id=current_user.id)
    return ApiResponse(data=None, message="Deck deleted successfully.")


# ============================================================
# /flashcard-decks/{id}/cards  (4 endpoints)
# ============================================================

@router.get(
    "/flashcard-decks/{deck_id}/cards",
    response_model=PaginationResponse[FlashcardResponse],
    summary="Danh sách thẻ trong một deck",
)
async def list_cards(
    deck_id: UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """**Lấy danh sách tất cả thẻ (Flashcard) trong một deck.**"""
    cards, total = await flashcard_card_service.get_cards(db, deck_id=deck_id, page=page, limit=limit)
    total_pages = ceil(total / limit) if total else 0
    return PaginationResponse(
        data=[FlashcardResponse.model_validate(c) for c in cards],
        meta=PaginationMetadata(page=page, limit=limit, total=total, total_pages=total_pages),
    )


@router.post(
    "/flashcard-decks/{deck_id}/cards",
    response_model=ApiResponse[FlashcardResponse],
    status_code=201,
    summary="Thêm thẻ mới vào deck",
)
async def create_card(
    deck_id: UUID,
    payload: FlashcardCreate,
    current_user=Depends(_require_content_manager),
    db: Session = Depends(get_db),
):
    """
    **Tạo thẻ từ vựng mới trong một deck.**

    - Trả về 409 nếu từ đã tồn tại trong deck này.
    """
    card = await flashcard_card_service.create_card(db, deck_id=deck_id, user_id=current_user.id, payload=payload)
    return ApiResponse(data=FlashcardResponse.model_validate(card), message="Card created successfully.")


@router.put(
    "/flashcard-decks/{deck_id}/cards/{card_id}",
    response_model=ApiResponse[FlashcardResponse],
    summary="Cập nhật thẻ trong deck",
)
async def update_card(
    deck_id: UUID,
    card_id: UUID,
    payload: FlashcardUpdate,
    current_user=Depends(_require_content_manager),
    db: Session = Depends(get_db),
):
    """**Cập nhật nội dung một thẻ flashcard.**"""
    card = await flashcard_card_service.update_card(
        db, deck_id=deck_id, card_id=card_id, user_id=current_user.id, payload=payload
    )
    return ApiResponse(data=FlashcardResponse.model_validate(card), message="Card updated successfully.")


@router.delete(
    "/flashcard-decks/{deck_id}/cards/{card_id}",
    response_model=ApiResponse[None],
    summary="Xóa mềm thẻ khỏi deck",
)
async def delete_card(
    deck_id: UUID,
    card_id: UUID,
    current_user=Depends(_require_content_manager),
    db: Session = Depends(get_db),
):
    """**Xóa mềm (soft delete) một thẻ flashcard.**"""
    await flashcard_card_service.soft_delete_card(
        db, deck_id=deck_id, card_id=card_id, user_id=current_user.id
    )
    return ApiResponse(data=None, message="Card deleted successfully.")


# ============================================================
# /flashcards  (3 endpoints + 1 import)
# ============================================================

@router.get(
    "/flashcards/due",
    response_model=ApiResponse[list],
    summary="Lấy thẻ cần ôn hôm nay",
)
async def get_due_cards(
    deck_id: Optional[UUID] = Query(None, description="Filter thẻ theo deck cụ thể"),
    limit: int = Query(20, ge=1, le=50, description="Số thẻ tối đa trả về"),
    current_user=Depends(_require_student),
    db: Session = Depends(get_db),
):
    """
    **Lấy danh sách thẻ cần ôn hôm nay.**

    - Trả về thẻ có `due_date <= now()` HOẶC thẻ mới chưa từng học (`state = new`).
    - Ưu tiên thẻ đã đến hạn trước, sau đó mới thêm thẻ mới.
    - Tối đa `limit` thẻ (mặc định 20).
    """
    cards_data = await flashcard_review_service.get_due_cards(
        db, user_id=current_user.id, deck_id=deck_id, limit=limit
    )

    result = []
    for item in cards_data:
        card = item["card"]
        review = item["review"]
        card_resp = FlashcardWithReviewResponse.model_validate(card)
        if review:
            card_resp.review_state = review.state.value if hasattr(review.state, "value") else review.state
            card_resp.due_date = review.due_date
            card_resp.stability = review.stability
            card_resp.difficulty = review.difficulty
        else:
            card_resp.review_state = "new"
        result.append(card_resp.model_dump())

    return ApiResponse(data=result, message=f"{len(result)} card(s) ready for review.")


@router.post(
    "/flashcards/reviews",
    response_model=ApiResponse[ReviewResponse],
    status_code=201,
    summary="Submit kết quả ôn thẻ (FSRS)",
)
async def submit_review(
    payload: ReviewSubmitRequest,
    current_user=Depends(_require_student),
    db: Session = Depends(get_db),
):
    """
    **Submit kết quả ôn tập một thẻ.**

    Rating:
    - `1` = Again (quên hoàn toàn)
    - `2` = Hard (nhớ mang máng, mất công)
    - `3` = Good (nhớ được nhưng chật vật)
    - `4` = Easy (nhớ ngay, không cần suy nghĩ)

    FSRSEngine sẽ tính toán `due_date` tiếp theo và trả về trạng thái FSRS mới.

    **Acceptance**: rating=3 với thẻ mới → `due_date` khoảng 4–8 ngày từ now.
    """
    review = await flashcard_review_service.submit_review(db, user_id=current_user.id, payload=payload)

    from datetime import datetime as _dt
    interval_days = (review.due_date - _dt.now(review.due_date.tzinfo)).days if review.due_date else 0

    return ApiResponse(
        data=ReviewResponse(
            card_id=review.card_id,
            state=review.state.value if hasattr(review.state, "value") else review.state,
            stability=review.stability,
            difficulty=review.difficulty,
            retrievability=review.retrievability,
            repetition_count=review.repetition_count,
            lapses=review.lapses,
            interval_days=max(0, interval_days),
            due_date=review.due_date,
            last_rating=review.last_rating.value if hasattr(review.last_rating, "value") else review.last_rating,
        ),
        message="Review submitted successfully.",
    )


@router.get(
    "/flashcards/stats",
    response_model=ApiResponse[FlashcardStatsResponse],
    summary="Thống kê cá nhân flashcard",
)
async def get_stats(
    current_user=Depends(_require_student),
    db: Session = Depends(get_db),
):
    """
    **Lấy thống kê ôn tập cá nhân.**

    Bao gồm:
    - `streak_days`: Số ngày liên tiếp ôn bài
    - `total_mastered`: Số thẻ đã thuộc (review ≥ 3 lần)
    - `due_today`: Số thẻ cần ôn hôm nay
    - `heatmap`: Hoạt động 30 ngày gần nhất (ngày + số thẻ)
    """
    stats_data = await flashcard_stats_service.get_stats(db, user_id=current_user.id)
    return ApiResponse(
        data=FlashcardStatsResponse(
            total_reviews=stats_data["total_reviews"],
            total_mastered=stats_data["total_mastered"],
            streak_days=stats_data["streak_days"],
            due_today=stats_data["due_today"],
            heatmap=[DailyActivity(**d) for d in stats_data["heatmap"]],
        )
    )


@router.post(
    "/flashcards/import-from-vocabulary",
    response_model=ApiResponse[dict],
    status_code=201,
    summary="Import từ vựng cá nhân vào deck",
)
async def import_from_vocabulary(
    payload: ImportFromVocabularyRequest,
    current_user=Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    **Import từ user_vocabulary sang Flashcard deck.**

    - Tự động bỏ qua các từ đã tồn tại trong deck.
    - Trả về số từ đã import thành công và số từ bị skip.
    """
    success_count, skipped_count = await flashcard_card_service.import_from_vocabulary(
        db, user_id=current_user.id, payload=payload
    )
    return ApiResponse(
        data={"imported": success_count, "skipped": skipped_count},
        message=f"Imported {success_count} card(s), skipped {skipped_count} duplicate(s).",
    )
