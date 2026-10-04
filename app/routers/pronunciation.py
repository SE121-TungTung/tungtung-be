import random
from typing import Optional, List, Dict
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
    DrillSuggestionsResponse,
)
from app.services.pronunciation_service import pronunciation_service

# Kho dữ liệu từ vựng và câu IELTS theo 6 chủ đề chuẩn
DRILL_TOPICS_DATA: Dict[str, List[str]] = {
    "environment": [
        "biodiversity conservation",
        "deforestation",
        "renewable energy source",
        "carbon footprint reduction",
        "greenhouse gas emissions",
        "ecosystem preservation",
        "sustainable agriculture",
        "climate change mitigation",
        "hazardous waste disposal",
        "ecological catastrophe",
        "The depletion of natural resources poses a severe threat to future generations.",
        "Governments worldwide must enact stringent environmental legislation.",
    ],
    "technology": [
        "artificial intelligence",
        "cybersecurity breach",
        "algorithmic decision making",
        "technological breakthrough",
        "cloud computing infrastructure",
        "virtual reality simulation",
        "autonomous vehicle",
        "biometric authentication",
        "machine learning model",
        "digital transformation",
        "Technological advancements have radically revolutionized our daily communication.",
        "Automation in manufacturing significantly boosts industrial productivity.",
    ],
    "health": [
        "cardiovascular disease",
        "sedentary lifestyle",
        "nutritional balance",
        "psychological well-being",
        "immune system resilience",
        "chronic illness management",
        "preventive healthcare",
        "epidemiological investigation",
        "therapeutic intervention",
        "metabolic rate",
        "Regular physical exercise is indispensable for maintaining cardiovascular health.",
        "A nutritious diet plays a pivotal role in preventing chronic disorders.",
    ],
    "education": [
        "curriculum development",
        "academic achievement",
        "pedagogical approach",
        "critical thinking skills",
        "vocational education",
        "distance learning platform",
        "interdisciplinary research",
        "educational inequality",
        "comprehensive assessment",
        "lifelong learning",
        "Fostering independent critical thinking should be the cornerstone of higher education.",
        "Interactive learning environments stimulate student engagement and academic excellence.",
    ],
    "travel": [
        "breathtaking panoramic view",
        "itinerary planning",
        "indigenous cultural heritage",
        "hospitality industry",
        "picturesque destination",
        "sustainable ecotourism",
        "cosmopolitan metropolis",
        "remote excursion",
        "scenic coastline",
        "historical monument",
        "Traveling to exotic destinations broadens one's cultural horizons significantly.",
        "Ecotourism encourages the preservation of delicate natural habitats.",
    ],
    "culture": [
        "multicultural diversity",
        "cultural assimilation",
        "traditional craftsmanship",
        "customary celebration",
        "intangible heritage",
        "linguistic preservation",
        "folklore and mythology",
        "societal norms",
        "cross-cultural understanding",
        "ancestral ritual",
        "Preserving intangible cultural heritage fosters a deep sense of communal identity.",
        "Cultural diversity enriches society through varied artistic and culinary expressions.",
    ],
}

router = APIRouter(
    prefix="/pronunciation",
    tags=["Pronunciation Practice"],
    route_class=ResponseWrapperRoute,
)


@router.get(
    "/drill-suggestions",
    response_model=ApiResponse[DrillSuggestionsResponse],
    summary="Gợi ý từ/câu luyện phát âm theo chủ đề IELTS",
    description="Trả về 5 từ hoặc cụm câu ngẫu nhiên từ kho từ vựng IELTS theo 6 chủ đề chính: environment, technology, health, education, travel, culture.",
)
async def get_drill_suggestions(
    topic: str = Query("environment", description="Chủ đề luyện tập: environment, technology, health, education, travel, culture"),
):
    topic_key = topic.strip().lower()
    if topic_key not in DRILL_TOPICS_DATA:
        topic_key = "environment"

    pool = DRILL_TOPICS_DATA[topic_key]
    sample_size = min(5, len(pool))
    sampled_items = random.sample(pool, sample_size)

    return ApiResponse(
        data=DrillSuggestionsResponse(topic=topic_key, items=sampled_items),
        message=f"Lấy 5 gợi ý luyện tập chủ đề {topic_key} thành công.",
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
    accent: Optional[str] = Form("US", description="Giọng chuẩn đối chiếu: US (Mỹ) hoặc UK (Anh)"),
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
        accent=accent or "US",
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


# ════════════════════════════════════════════════════════════
# PHONEME MASTERY — Progress & Spaced Repetition endpoints
# ════════════════════════════════════════════════════════════

@router.get(
    "/mastery/summary",
    summary="Tổng hợp mastery theo nhóm âm (Radar Chart data)",
    description="Trả về mastery trung bình theo 8 nhóm âm (Stops, Fricatives...), "
                "tổng phonemes mastered/learning/unseen, và số phoneme cần ôn.",
)
async def get_mastery_summary(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    summary = pronunciation_service.get_phoneme_mastery_summary(
        db=db, student_id=current_user.id
    )
    return ApiResponse(data=summary, message="Lấy mastery summary thành công.")


@router.get(
    "/mastery/review-queue",
    summary="Danh sách phoneme cần ôn tập (Spaced Repetition)",
    description="Trả về phonemes có next_review_at <= now, sắp xếp theo mastery thấp nhất.",
)
async def get_review_queue(
    limit: int = Query(10, ge=1, le=30, description="Số phoneme tối đa"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    items = pronunciation_service.get_due_for_review(
        db=db, student_id=current_user.id, limit=limit
    )
    return ApiResponse(
        data={"due_phonemes": items, "count": len(items)},
        message=f"Có {len(items)} âm cần ôn tập.",
    )


@router.get(
    "/mastery/map",
    summary="Bản đồ 44 phoneme IPA với mã màu mastery",
    description="Trả về danh sách 44 phoneme với mastery_level, avg_score, status (unseen/learning/familiar/practiced/mastered).",
)
async def get_mastery_map(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    phoneme_map = pronunciation_service.get_phoneme_mastery_map(
        db=db, student_id=current_user.id
    )
    return ApiResponse(
        data={"phonemes": phoneme_map},
        message="Lấy phoneme mastery map thành công.",
    )


# ════════════════════════════════════════════════════════════
# ASSESSMENT (Placement Test) endpoints
# ════════════════════════════════════════════════════════════

@router.get(
    "/assessment/items",
    summary="Lấy danh sách items cho Placement Test",
    description="Trả về 10 từ/câu mẫu bao phủ 8 nhóm âm để đánh giá trình độ.",
)
async def get_assessment_items(
    current_user: User = Depends(get_current_active_user),
):
    items = pronunciation_service.get_assessment_items()
    return ApiResponse(
        data={"items": items, "total": len(items)},
        message="Lấy assessment items thành công.",
    )


@router.post(
    "/assessment",
    status_code=status.HTTP_201_CREATED,
    summary="Nộp kết quả Placement Test",
    description="Gửi kết quả đánh giá từng item, hệ thống sẽ phân tích weak/strong phonemes và ước lượng CEFR/IELTS.",
)
async def submit_assessment(
    request_body: dict,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    items = request_body.get("items", [])
    if not items:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="items không được để trống.")

    result = pronunciation_service.submit_assessment(
        db=db,
        student_id=current_user.id,
        items=items,
    )
    return ApiResponse(
        data=result,
        message="Đánh giá trình độ phát âm hoàn tất.",
    )


@router.get(
    "/assessment/latest",
    summary="Lấy kết quả Placement Test gần nhất",
    description="Trả về kết quả assessment gần nhất (CEFR, IELTS estimate, weak phonemes).",
)
async def get_latest_assessment(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    result = pronunciation_service.get_latest_assessment(
        db=db, student_id=current_user.id
    )
    if not result:
        return ApiResponse(
            data=None,
            message="Chưa có bài đánh giá nào. Hãy làm Placement Test.",
        )
    return ApiResponse(data=result, message="Lấy assessment thành công.")


# ════════════════════════════════════════════════════════════
# DAILY MISSIONS endpoints
# ════════════════════════════════════════════════════════════

@router.get(
    "/missions/today",
    summary="Nhiệm vụ luyện tập cá nhân hóa hôm nay",
    description="Tạo 5-8 missions dựa trên SR review queue, weak phonemes, new phonemes, và sentence drills.",
)
async def get_daily_missions(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    missions = pronunciation_service.get_daily_missions(
        db=db, student_id=current_user.id
    )
    return ApiResponse(
        data=missions,
        message=f"Có {missions['total_missions']} nhiệm vụ hôm nay.",
    )
