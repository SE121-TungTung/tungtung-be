"""
Model: user_vocabulary
Mục đích: Sổ tay từ vựng cá nhân của học viên
Spec ref: ielts_system_spec_part2.md § 3.2.3 & § 4.2
"""
from sqlalchemy import Column, String, Text, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.models.base import BaseModel
import uuid


class UserVocabulary(BaseModel):
    __tablename__ = "user_vocabulary"
    __table_args__ = (
        # Đảm bảo mỗi user không lưu trùng từ từ cùng 1 passage
        Index(
            "uq_user_vocab_word_passage",
            "user_id",
            "word",
            "source_passage_id",
            unique=True,
            postgresql_where=None  # cho phép null source_passage_id
        ),
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Từ vựng
    word = Column(String(200), nullable=False)
    ipa = Column(String(200))                   # Phiên âm IPA: /ɪˈnvaɪ.rən.mənt/
    meaning_vi = Column(Text)                   # Nghĩa tiếng Việt
    example = Column(Text)                      # Câu ví dụ tiếng Anh
    word_type = Column(String(50))              # noun, verb, adj, adv, phrase...

    # Metadata nguồn
    source_passage_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_passages.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Mức độ thuộc từ: 0=new, 1=learning, 2=familiar, 3=mastered
    mastery_level = Column(Integer, default=0, nullable=False)
