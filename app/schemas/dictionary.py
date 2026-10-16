from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class IpaBatchRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1, max_length=20)

    @field_validator("texts")
    @classmethod
    def _strip(cls, v: List[str]) -> List[str]:
        cleaned = [t.strip()[:500] for t in v if t and t.strip()]
        if not cleaned:
            raise ValueError("texts must contain at least one non-empty string")
        return cleaned


class IpaItem(BaseModel):
    text: str
    ipa_us: Optional[str] = None
    ipa_uk: Optional[str] = None
    source: str = "none"  # cache | dictionary | ai | none


class IpaBatchResponse(BaseModel):
    items: List[IpaItem]
