"""
Service: SpeakingRandomService
Spec ref: ielts_system_spec_part2.md § 3.3 — Speaking Random Part 1

Logic:
  1. Query QuestionBank WHERE:
       skill_area = 'speaking'
       question_type = 'speaking_part_1'
       status = 'active'
       deleted_at IS NULL
  2. Group theo tags->>'topic'
  3. Shuffle topics → lấy `num_topics` topics ngẫu nhiên
  4. Mỗi topic lấy ngẫu nhiên `questions_per_topic` câu (mặc định 3-4)
  5. Trả về SpeakingPart1Response (in-memory, không persist DB)
"""
import random
from collections import defaultdict
from typing import Dict, List
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.models.test import QuestionBank, QuestionType, SkillArea, ContentStatus
from app.schemas.speaking_random import (
    SpeakingPart1Response,
    SpeakingTopicGroup,
    SpeakingQuestionItem,
)

_DEFAULT_TOPIC = "general"          # fallback nếu câu hỏi không có tag topic
_DEFAULT_QUESTIONS_PER_TOPIC = 4    # số câu mỗi topic (trừ khi topic ít hơn)
_MAX_QUESTIONS_PER_TOPIC = 5


class SpeakingRandomService:

    def get_random_part1(
        self,
        db: Session,
        num_topics: int = 3,
        questions_per_topic: int = _DEFAULT_QUESTIONS_PER_TOPIC,
    ) -> SpeakingPart1Response:
        """
        Lấy ngẫu nhiên `num_topics` topics từ Speaking Part 1 question bank.

        Args:
            num_topics: Số topics cần lấy (default 3, max 10)
            questions_per_topic: Số câu mỗi topic (default 4, max 5)
        """
        num_topics = max(1, min(num_topics, 10))
        questions_per_topic = max(1, min(questions_per_topic, _MAX_QUESTIONS_PER_TOPIC))

        # 1. Query toàn bộ Speaking Part 1 active questions
        questions: List[QuestionBank] = (
            db.query(QuestionBank)
            .filter(
                QuestionBank.skill_area == SkillArea.SPEAKING.value,
                QuestionBank.question_type == QuestionType.SPEAKING_PART_1.value,
                QuestionBank.status == ContentStatus.ACTIVE.value,
                QuestionBank.deleted_at.is_(None),
            )
            .all()
        )

        if not questions:
            raise APIException(
                status_code=404,
                code="NO_SPEAKING_QUESTIONS",
                message="No Speaking Part 1 questions are available in the question bank.",
            )

        # 2. Group theo topic tag
        topic_map: Dict[str, List[QuestionBank]] = defaultdict(list)
        for q in questions:
            # tags có thể là dict hoặc None
            topic = _DEFAULT_TOPIC
            if isinstance(q.tags, dict):
                topic = q.tags.get("topic", _DEFAULT_TOPIC) or _DEFAULT_TOPIC
            elif isinstance(q.tags, list):
                # Nếu tags lưu dạng array string thì dùng general
                topic = _DEFAULT_TOPIC
            topic_map[topic].append(q)

        available_topics = list(topic_map.keys())

        if not available_topics:
            raise APIException(
                status_code=404,
                code="NO_SPEAKING_TOPICS",
                message="No topics found for Speaking Part 1.",
            )

        # 3. Shuffle và chọn num_topics topics ngẫu nhiên
        random.shuffle(available_topics)
        selected_topics = available_topics[:num_topics]

        # 4. Build response
        topic_groups: List[SpeakingTopicGroup] = []

        for topic in selected_topics:
            pool = topic_map[topic]
            # Shuffle câu hỏi trong topic rồi lấy questions_per_topic câu
            random.shuffle(pool)
            chosen = pool[:questions_per_topic]

            topic_groups.append(
                SpeakingTopicGroup(
                    topic=topic,
                    questions=[
                        SpeakingQuestionItem(
                            id=q.id,
                            question_text=q.question_text,
                            difficulty_level=(
                                q.difficulty_level.value
                                if hasattr(q.difficulty_level, "value")
                                else q.difficulty_level
                            ),
                            tags=q.tags,
                        )
                        for q in chosen
                    ],
                    question_count=len(chosen),
                )
            )

        return SpeakingPart1Response(
            num_topics=len(topic_groups),
            topics=topic_groups,
        )


# Singleton instance
speaking_random_service = SpeakingRandomService()
