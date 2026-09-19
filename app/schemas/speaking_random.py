"""
Schemas: Speaking Random Part 1
Spec ref: ielts_system_spec_part2.md § 3.3

GET /tests/speaking/random-part1?num_topics=3
Response: SpeakingPart1Response — in-memory, không persist vào DB

Cấu trúc trả về:
  SpeakingPart1Response
    ├── topics: List[SpeakingTopicGroup]
    │     └── questions: List[SpeakingQuestionItem]
    └── total_questions: int
"""
from typing import List, Optional, Any
from uuid import UUID
from pydantic import BaseModel, Field


class SpeakingQuestionItem(BaseModel):
    """Một câu hỏi Speaking Part 1."""
    id: UUID
    question_text: str
    difficulty_level: Optional[str] = None
    tags: Optional[Any] = None

    model_config = {"from_attributes": True}


class SpeakingTopicGroup(BaseModel):
    """Một nhóm câu hỏi theo topic."""
    topic: str
    questions: List[SpeakingQuestionItem]
    question_count: int


class SpeakingPart1Response(BaseModel):
    """
    In-memory Speaking Part 1 session.
    Không có test_id thật — frontend dùng structure này để render câu hỏi.
    """
    skill_area: str = "speaking"
    question_type: str = "speaking_part_1"
    num_topics: int
    topics: List[SpeakingTopicGroup]
    total_questions: int = Field(default=0)

    def model_post_init(self, __context: Any) -> None:
        # Tự tính total_questions sau khi khởi tạo
        object.__setattr__(
            self,
            "total_questions",
            sum(g.question_count for g in self.topics)
        )

    model_config = {"from_attributes": True}
