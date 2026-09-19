"""
Service: DictationService
Spec ref: ielts_system_spec_part2.md § 3.2 — Dictation Mode

Logic:
  - Nhận test_id → tìm section Listening → lấy tất cả parts có passage/audio
  - Parse text_content thành list DictationSegment
  - Hỗ trợ 2 format của text_content:
      1. JSON array: [{"text": "...", "start_ms": 0, "end_ms": 3500}, ...]
         → timestamps chính xác, dùng cho audio có SRT/VTT đã process
      2. Plain text: "Sentence one. Sentence two. Sentence three."
         → auto-split thành câu, không có timestamp
"""
import json
import re
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import APIException
from app.models.test import (
    Test,
    TestSection,
    TestSectionPart,
    ContentPassage,
    SkillArea,
)
from app.schemas.dictation import DictationSegment, DictationPartResponse, DictationResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_plain_text_into_sentences(text: str) -> List[str]:
    """
    Split plain text thành câu.
    Pattern: dấu . ! ? theo sau bởi khoảng trắng hoặc ký tự hoa (không split trường hợp như "Mr.")
    """
    # Làm sạch whitespace thừa
    text = re.sub(r"\s+", " ", text.strip())
    # Split theo dấu câu kết thúc (.!?) nhưng giữ lại nếu sau đó là số (8.5 v.v.)
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'(])', text)
    return [s.strip() for s in sentences if s.strip()]


def _parse_text_content(text_content: Optional[str]) -> List[DictationSegment]:
    """
    Parse text_content thành list DictationSegment.
    Trả về [] nếu text_content là None hoặc rỗng.
    """
    if not text_content or not text_content.strip():
        return []

    stripped = text_content.strip()

    # Thử parse JSON
    if stripped.startswith("["):
        try:
            raw_list = json.loads(stripped)
            if isinstance(raw_list, list):
                segments = []
                for idx, item in enumerate(raw_list):
                    if isinstance(item, dict) and "text" in item:
                        segments.append(
                            DictationSegment(
                                segment_index=idx,
                                text=item["text"].strip(),
                                start_ms=item.get("start_ms"),
                                end_ms=item.get("end_ms"),
                            )
                        )
                    elif isinstance(item, str):
                        # Fallback: JSON array of strings
                        segments.append(
                            DictationSegment(
                                segment_index=idx,
                                text=item.strip(),
                                start_ms=None,
                                end_ms=None,
                            )
                        )
                return segments
        except (json.JSONDecodeError, ValueError):
            pass  # Fallback sang plain text

    # Plain text → split thành câu
    sentences = _split_plain_text_into_sentences(stripped)
    return [
        DictationSegment(
            segment_index=idx,
            text=sentence,
            start_ms=None,
            end_ms=None,
        )
        for idx, sentence in enumerate(sentences)
    ]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class DictationService:

    def get_dictation_segments(
        self,
        db: Session,
        test_id: UUID,
    ) -> DictationResponse:
        """
        Lấy tất cả dictation segments cho một test.

        - Chỉ xử lý sections có skill_area = LISTENING.
        - Mỗi Part sẽ thành 1 DictationPartResponse với audio_url + list segments.
        - Nếu test không có section Listening → trả 404.
        """
        # 1. Load test + listening sections
        test = (
            db.query(Test)
            .options(
                joinedload(Test.sections)
                .joinedload(TestSection.parts)
                .joinedload(TestSectionPart.passage)
            )
            .filter(
                Test.id == test_id,
                Test.deleted_at.is_(None),
            )
            .first()
        )

        if not test:
            raise APIException(
                status_code=404,
                code="TEST_NOT_FOUND",
                message="Test not found.",
            )

        # 2. Lọc section Listening
        listening_sections = [
            sec for sec in (test.sections or [])
            if sec.skill_area == SkillArea.LISTENING.value
            or sec.skill_area == SkillArea.LISTENING
        ]

        if not listening_sections:
            raise APIException(
                status_code=404,
                code="NO_LISTENING_SECTION",
                message="This test has no Listening section. Dictation mode is only available for Listening tests.",
            )

        # 3. Build DictationPartResponse cho từng part
        parts_result: List[DictationPartResponse] = []

        for section in listening_sections:
            for part in sorted(section.parts or [], key=lambda p: p.order_number):
                # Ưu tiên audio_url của Part trực tiếp, fallback sang Passage
                audio_url: Optional[str] = part.audio_url

                passage: Optional[ContentPassage] = part.passage
                if not audio_url and passage:
                    audio_url = passage.audio_url

                # Lấy text để parse segment
                text_content: Optional[str] = passage.text_content if passage else None
                duration_seconds: Optional[int] = passage.duration_seconds if passage else None

                segments = _parse_text_content(text_content)

                parts_result.append(
                    DictationPartResponse(
                        part_id=part.id,
                        part_name=part.name,
                        part_order=part.order_number,
                        audio_url=audio_url,
                        duration_seconds=duration_seconds,
                        total_segments=len(segments),
                        segments=segments,
                    )
                )

        return DictationResponse(
            test_id=test_id,
            test_title=test.title,
            parts=parts_result,
        )


# Singleton instance
dictation_service = DictationService()
