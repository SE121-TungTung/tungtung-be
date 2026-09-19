"""
Schemas: Vocabulary
Spec ref: ielts_system_spec_part2.md § 3.2.3 & § 4.2
"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

from app.schemas.base_schema import ApiResponse, PaginationResponse


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class VocabularySaveRequest(BaseModel):
    """POST /vocabulary/save — Lưu 1 từ vào sổ tay cá nhân."""
    word: str = Field(..., max_length=200, description="Từ cần lưu")
    ipa: Optional[str] = Field(None, max_length=200, description="Phiên âm IPA, VD: /ɪˈnvaɪ.rən.mənt/")
    meaning_vi: Optional[str] = Field(None, description="Nghĩa tiếng Việt")
    example: Optional[str] = Field(None, description="Câu ví dụ tiếng Anh")
    word_type: Optional[str] = Field(None, max_length=50, description="noun | verb | adj | adv | phrase")
    source_passage_id: Optional[UUID] = Field(None, description="ID bài đọc/nghe mà từ được lấy")


class VocabularyUpdateRequest(BaseModel):
    """PATCH /vocabulary/{id} — Cập nhật mức độ thuộc từ."""
    mastery_level: int = Field(..., ge=0, le=3, description="0=new, 1=learning, 2=familiar, 3=mastered")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class VocabularyResponse(BaseModel):
    """Đại diện 1 mục từ vựng trả về client."""
    id: UUID
    user_id: UUID
    word: str
    ipa: Optional[str] = None
    meaning_vi: Optional[str] = None
    example: Optional[str] = None
    word_type: Optional[str] = None
    source_passage_id: Optional[UUID] = None
    mastery_level: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Typed response wrappers (dùng generic ApiResponse / PaginationResponse)
# ---------------------------------------------------------------------------

VocabularyApiResponse = ApiResponse[VocabularyResponse]
VocabularyListResponse = PaginationResponse[VocabularyResponse]
