from sqlalchemy import Column, String, Text, Integer, Index, text
from app.models.base import BaseModel


class PronunciationPracticeItem(BaseModel):
    """
    Kho bài luyện phát âm dùng chung, do AI sinh ra và được tái sử dụng.
    - kind: roadmap | phoneme | drill
    - context_key: ngữ cảnh của bài, ví dụ "level:1", "phoneme:θ", "topic:environment"
    - text_key: bản chuẩn hoá (lowercase) để chống trùng trong cùng (kind, context_key)
    """
    __tablename__ = "pronunciation_practice_items"
    __table_args__ = (
        Index("idx_pron_practice_items_ctx", "kind", "context_key"),
        Index(
            "uq_pron_practice_items_ctx_text",
            "kind", "context_key", "text_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    kind = Column(String(20), nullable=False)
    context_key = Column(String(120), nullable=False)
    text = Column(String(500), nullable=False)
    text_key = Column(String(500), nullable=False)
    target_type = Column(String(20), nullable=False, default="word")
    ipa_us = Column(String(500), nullable=True)
    ipa_uk = Column(String(500), nullable=True)
    hint = Column(Text, nullable=True)
    usage_count = Column(Integer, nullable=False, default=0)
