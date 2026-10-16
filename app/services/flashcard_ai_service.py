"""
Service: Flashcard AI
- extract: trích xuất từ vựng đáng học từ một đoạn văn bản
- enrich:  sinh IPA, từ loại, nghĩa Việt/Anh, câu ví dụ cho danh sách từ cho trước

Gọi Gemini REST qua httpx (cùng cách với dictionary_service). Kết quả chỉ là GỢI Ý,
không ghi DB; người dùng review rồi mới lưu qua endpoint bulk.
"""
import json
import logging
import os
from typing import List, Optional

import httpx

from app.core.config import settings
from app.core.exceptions import APIException
from app.models.flashcard import WordType
from app.services.gemini_client import call_gemini_json

logger = logging.getLogger(__name__)

_VALID_WORD_TYPES = {wt.value for wt in WordType}
_WORD_TYPE_ALIASES = {
    "adj": "adjective", "adv": "adverb", "n": "noun", "v": "verb",
    "phrasal verb": "phrase", "idiom": "phrase", "collocation": "phrase",
    "prep": "preposition", "conj": "conjunction", "pron": "pronoun",
}


def _normalize_word_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().lower()
    v = _WORD_TYPE_ALIASES.get(v, v)
    return v if v in _VALID_WORD_TYPES else None


def _clean_ipa(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().strip("/").strip()
    return v or None


class FlashcardAIService:
    async def generate(
        self,
        *,
        mode: str,
        text: Optional[str],
        words: Optional[List[str]],
        max_items: int,
        level: Optional[str],
        topic: Optional[str],
    ) -> List[dict]:
        api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise APIException(
                status_code=503,
                code="AI_NOT_CONFIGURED",
                message="Dịch vụ AI chưa được cấu hình (thiếu GEMINI_API_KEY).",
            )

        prompt = self._build_prompt(mode, text, words, max_items, level, topic)
        raw_items = await self._call_gemini(api_key, prompt)
        return self._sanitize(raw_items, mode, words, max_items)

    # ------------------------------------------------------------------
    def _build_prompt(self, mode, text, words, max_items, level, topic) -> str:
        schema = (
            "Return ONLY a raw JSON array (no markdown). Each element is an object with string keys: "
            "'word' (lowercase base form, or the phrase), "
            "'ipa' (IPA without slashes, empty string if unsure), "
            "'word_type' (one of: noun, verb, adjective, adverb, pronoun, preposition, conjunction, "
            "interjection, phrase), "
            "'definition_vi' (concise Vietnamese meaning fitting this context), "
            "'definition_en' (short, clear English definition), "
            "'example_sentence' (one natural English example sentence). "
            "Never invent words that are not real English."
        )
        level_hint = f" Target learner level: {level}." if level else ""
        topic_hint = f" Topic: {topic}." if topic else ""

        if mode == "enrich":
            word_list = "\n".join(f"- {w}" for w in (words or []))
            return (
                "You are an English vocabulary teacher for Vietnamese learners."
                f"{level_hint}{topic_hint} Create flashcard data for EXACTLY these words, "
                f"one object per word, keeping the given words:\n{word_list}\n\n{schema}"
            )

        return (
            "You are an English vocabulary teacher for Vietnamese learners."
            f"{level_hint}{topic_hint} From the text below, pick up to {max_items} useful, "
            "non-trivial words or phrases worth studying (skip very basic words, names and numbers). "
            "Give the definition that matches the meaning in the text.\n\n"
            f"TEXT:\n\"\"\"\n{text}\n\"\"\"\n\n{schema}"
        )

    async def _call_gemini(self, api_key: str, prompt: str) -> list:
        try:
            parsed = await call_gemini_json(prompt, temperature=0.3, timeout=45.0)
            if isinstance(parsed, dict):
                parsed = parsed.get("cards") or parsed.get("words") or parsed.get("items") or []
            return parsed if isinstance(parsed, list) else []
        except APIException:
            raise
        except Exception as e:
            logger.error("Flashcard AI unexpected error: %s", e)
            raise APIException(status_code=502, code="AI_FAILED", message="AI không phản hồi hợp lệ, vui lòng thử lại.")

    def _sanitize(self, raw_items: list, mode: str, words: Optional[List[str]], max_items: int) -> List[dict]:
        results: List[dict] = []
        seen = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            word = str(item.get("word", "")).strip()[:200]
            key = word.lower()
            if not word or key in seen:
                continue
            seen.add(key)
            results.append({
                "word": word,
                "ipa": _clean_ipa(item.get("ipa")),
                "word_type": _normalize_word_type(item.get("word_type")),
                "definition_vi": (str(item.get("definition_vi") or "").strip() or None),
                "definition_en": (str(item.get("definition_en") or "").strip() or None),
                "example_sentence": (str(item.get("example_sentence") or "").strip() or None),
            })
        limit = len(words) if mode == "enrich" and words else max_items
        return results[:limit]


flashcard_ai_service = FlashcardAIService()
