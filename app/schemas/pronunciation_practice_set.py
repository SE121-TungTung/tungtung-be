from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class PracticeSetGenerateRequest(BaseModel):
    kind: Literal["roadmap", "phoneme", "drill"]
    level: Optional[int] = Field(None, ge=1, le=4)        # roadmap
    phoneme: Optional[str] = Field(None, max_length=10)   # phoneme (ký hiệu IPA, vd "θ")
    topic: Optional[str] = Field(None, max_length=80)     # drill (key có sẵn hoặc chủ đề tự nhập)
    count: int = Field(10, ge=4, le=15)
    exclude: List[str] = Field(default_factory=list, max_length=60)

    @field_validator("phoneme")
    @classmethod
    def _strip_phoneme(cls, v):
        return v.strip().strip("/") if v else v

    @field_validator("topic")
    @classmethod
    def _strip_topic(cls, v):
        return " ".join(v.split()) if v else v

    @model_validator(mode="after")
    def _check_context(self):
        if self.kind == "roadmap" and not self.level:
            raise ValueError("level is required for kind=roadmap")
        if self.kind == "phoneme" and not self.phoneme:
            raise ValueError("phoneme is required for kind=phoneme")
        if self.kind == "drill" and not self.topic:
            raise ValueError("topic is required for kind=drill")
        return self


class PracticeSetItem(BaseModel):
    id: str
    text: str
    target_type: str = "word"
    ipa_us: Optional[str] = None
    ipa_uk: Optional[str] = None
    hint: Optional[str] = None


class PracticeSetResponse(BaseModel):
    kind: str
    context_key: str
    items: List[PracticeSetItem]
    generated_new: int = 0   # số bài vừa được AI sinh thêm vào kho
    from_pool: int = 0       # số bài lấy từ kho dùng chung


class DrillTopic(BaseModel):
    key: str
    label: str


class DrillTopicsResponse(BaseModel):
    topics: List[DrillTopic]
