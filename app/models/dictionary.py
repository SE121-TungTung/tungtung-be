from sqlalchemy import Column, String, Text
from app.models.base import BaseModel

class DictionaryWord(BaseModel):
    __tablename__ = "dictionary_words"

    word = Column(String(255), unique=True, index=True, nullable=False)
    ipa = Column(String(255), nullable=True)
    word_type = Column(String(50), nullable=True)
    definition_en = Column(Text, nullable=True)
    example_sentence = Column(Text, nullable=True)
