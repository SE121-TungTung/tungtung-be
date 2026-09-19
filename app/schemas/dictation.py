"""
Schemas: Dictation Mode
Spec ref: ielts_system_spec_part2.md § 3.2

GET /tests/{test_id}/dictation-segments
Response: DictationResponse
  └── parts: List[DictationPartResponse]
        └── segments: List[DictationSegment]
"""
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel


class DictationSegment(BaseModel):
    """Một câu/đoạn để học dictation."""
    segment_index: int
    text: str
    # Timestamps nếu có audio đã được xử lý SRT/VTT
    start_ms: Optional[int] = None   # Thời điểm bắt đầu (milliseconds)
    end_ms: Optional[int] = None     # Thời điểm kết thúc (milliseconds)

    model_config = {"from_attributes": True}


class DictationPartResponse(BaseModel):
    """Một Part trong bài Listening (Section 1, 2, 3, 4...)."""
    part_id: UUID
    part_name: str
    part_order: int
    audio_url: Optional[str] = None       # URL file audio để nghe
    duration_seconds: Optional[int] = None  # Độ dài audio (giây)
    total_segments: int                    # Tổng số câu/đoạn
    segments: List[DictationSegment]

    model_config = {"from_attributes": True}


class DictationResponse(BaseModel):
    """Response toàn bộ dictation data cho 1 test."""
    test_id: UUID
    test_title: str
    parts: List[DictationPartResponse]

    @property
    def total_parts(self) -> int:
        return len(self.parts)

    @property
    def total_segments(self) -> int:
        return sum(p.total_segments for p in self.parts)

    model_config = {"from_attributes": True}
