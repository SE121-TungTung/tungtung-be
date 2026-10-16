"""
Service: Pronunciation Practice Sets
Sinh bộ bài luyện phát âm (roadmap / theo âm / drill theo chủ đề) bằng AI và lưu vào
kho dùng chung `pronunciation_practice_items`.

Luồng: lấy từ kho trước -> nếu kho chưa đủ phong phú thì gọi AI sinh thêm (loại trừ bài
đã có) -> lưu kho -> trả bộ bài ngẫu nhiên. Lỗi AI: nếu kho còn đủ bài thì vẫn dùng kho,
ngược lại báo "AI server đang lỗi, hãy thử lại sau".
"""
import logging
import random
import re
from typing import Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.repositories.pronunciation_practice_item import pronunciation_practice_item_repo as repo
from app.schemas.pronunciation_practice_set import (
    PracticeSetGenerateRequest, PracticeSetItem, PracticeSetResponse,
    DrillTopic,
)
from app.services.gemini_client import call_gemini_json, AI_ERROR_MESSAGE

logger = logging.getLogger(__name__)

# Chủ đề Drill (key -> nhãn hiển thị tiếng Việt, tên tiếng Anh dùng trong prompt)
DRILL_TOPICS: List[Dict[str, str]] = [
    {"key": "environment", "label": "Môi trường", "en": "Environment"},
    {"key": "technology", "label": "Công nghệ", "en": "Technology"},
    {"key": "health", "label": "Sức khỏe", "en": "Health"},
    {"key": "education", "label": "Giáo dục", "en": "Education"},
    {"key": "travel", "label": "Du lịch", "en": "Travel and tourism"},
    {"key": "culture", "label": "Văn hóa", "en": "Culture and traditions"},
    {"key": "work", "label": "Công việc", "en": "Work and careers"},
    {"key": "media", "label": "Truyền thông", "en": "Media and advertising"},
    {"key": "crime", "label": "Tội phạm & luật pháp", "en": "Crime and law"},
    {"key": "urbanization", "label": "Đô thị hóa", "en": "Urbanization and housing"},
    {"key": "economy", "label": "Kinh tế", "en": "Economy and finance"},
    {"key": "science", "label": "Khoa học", "en": "Science and research"},
    {"key": "family", "label": "Gia đình & xã hội", "en": "Family and society"},
    {"key": "food", "label": "Ẩm thực", "en": "Food and diet"},
]
_TOPIC_BY_KEY = {t["key"]: t for t in DRILL_TOPICS}

_LEVEL_FOCUS: Dict[int, Dict[str, str]] = {
    1: {
        "target_type": "word",
        "desc": "single English words that contrast easily confused sounds (minimal pairs such as "
                "sheep/ship, light/right, think/sink, vowel length and final consonants)",
    },
    2: {
        "target_type": "word",
        "desc": "useful IELTS vocabulary with 3-4 syllables and tricky word stress or silent letters",
    },
    3: {
        "target_type": "sentence",
        "desc": "natural sentences of 6-12 words that practise linking, weak forms and consonant clusters",
    },
    4: {
        "target_type": "sentence",
        "desc": "IELTS Speaking style sentences of 12-20 words that need natural rhythm, stress "
                "and intonation",
    },
}

_SAFE_TOPIC_RE = re.compile(r"[^a-zA-Z0-9\u00C0-\u1EF9 ,'\-]")


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _ai_error() -> APIException:
    return APIException(status_code=503, code="AI_UNAVAILABLE", message=AI_ERROR_MESSAGE)


class PronunciationPracticeSetService:
    def list_topics(self) -> List[DrillTopic]:
        return [DrillTopic(key=t["key"], label=t["label"]) for t in DRILL_TOPICS]

    # ------------------------------------------------------------------
    async def generate(
        self, db: Session, user_id: UUID, payload: PracticeSetGenerateRequest
    ) -> PracticeSetResponse:
        kind = payload.kind
        context_key, context_desc = self._context(payload)
        count = payload.count
        exclude_keys: Set[str] = {_norm(e) for e in payload.exclude if e and e.strip()}

        pool = repo.list_by_context(db, kind, context_key)
        unseen = [p for p in pool if p.text_key not in exclude_keys]

        new_items = []
        # Kho chưa đủ phong phú -> nhờ AI sinh thêm
        if len(unseen) < count * 2:
            known_keys = {p.text_key for p in pool} | exclude_keys
            try:
                raw = await self._ask_ai(payload, context_desc, known_keys)
                rows = self._sanitize(raw, payload, context_key, known_keys, user_id)
                new_items = repo.create_many(db, rows)
            except APIException:
                if len(unseen) < 3:
                    raise
                logger.warning("AI failed, falling back to practice pool for %s", context_key)
            else:
                if not new_items and len(unseen) < 3:
                    raise _ai_error()

        chosen = list(new_items[:count])
        remaining = count - len(chosen)
        if remaining > 0:
            new_ids = {n.id for n in chosen}
            rest = [p for p in unseen if p.id not in new_ids]
            random.shuffle(rest)
            chosen.extend(rest[:remaining])

        random.shuffle(chosen)
        repo.increment_usage(db, [c.id for c in chosen])

        return PracticeSetResponse(
            kind=kind,
            context_key=context_key,
            items=[
                PracticeSetItem(
                    id=str(c.id), text=c.text, target_type=c.target_type,
                    ipa_us=c.ipa_us, ipa_uk=c.ipa_uk, hint=c.hint,
                )
                for c in chosen
            ],
            generated_new=len(new_items),
            from_pool=max(len(chosen) - len(new_items), 0),
        )

    # ------------------------------------------------------------------
    def _context(self, payload: PracticeSetGenerateRequest):
        if payload.kind == "roadmap":
            focus = _LEVEL_FOCUS[payload.level]
            return f"level:{payload.level}", f"Roadmap level {payload.level}: {focus['desc']}"
        if payload.kind == "phoneme":
            sym = payload.phoneme
            return (
                f"phoneme:{sym}",
                f"words that clearly contain the English sound /{sym}/ "
                f"(prefer common words; a mix of initial, medial and final positions)",
            )
        # drill
        raw = payload.topic.strip()
        key = raw.lower()
        if key in _TOPIC_BY_KEY:
            return f"topic:{key}", f"IELTS topic \"{_TOPIC_BY_KEY[key]['en']}\""
        safe = _SAFE_TOPIC_RE.sub("", raw).strip()[:60]
        if not safe:
            raise APIException(status_code=422, code="INVALID_TOPIC", message="Chủ đề không hợp lệ.")
        return f"topic:{safe.lower()}", f"IELTS topic \"{safe}\""

    async def _ask_ai(
        self, payload: PracticeSetGenerateRequest, context_desc: str, known_keys: Set[str]
    ) -> list:
        # Giới hạn danh sách tránh trùng để prompt gọn
        avoid = sorted(known_keys)[:50]
        avoid_txt = ("\nDo NOT repeat any of these:\n" + "\n".join(f"- {a}" for a in avoid)) if avoid else ""
        n = payload.count

        if payload.kind == "roadmap":
            tt = _LEVEL_FOCUS[payload.level]["target_type"]
            task = f"Create {n} pronunciation practice items. Focus: {context_desc}. All items must have target_type \"{tt}\"."
        elif payload.kind == "phoneme":
            task = (
                f"Create {n} pronunciation practice words for the sound /{payload.phoneme}/: {context_desc}. "
                "Every item must have target_type \"word\" and its IPA MUST contain that sound."
            )
        else:
            task = (
                f"Create {n} pronunciation practice items for {context_desc}: about 60% useful academic "
                "words or collocations (target_type \"word\") and 40% natural sentences of 10-18 words "
                "(target_type \"sentence\")."
            )

        prompt = (
            "You are an English pronunciation coach for Vietnamese IELTS learners.\n"
            f"{task}{avoid_txt}\n\n"
            "Return ONLY a raw JSON array. Each element is an object with string keys: "
            "'text' (the word or sentence), "
            "'target_type' ('word' or 'sentence'), "
            "'ipa_us' (American IPA of the whole text, no slashes), "
            "'ipa_uk' (British RP IPA of the whole text, no slashes), "
            "'hint' (one short Vietnamese tip about the tricky sound or stress, max 120 chars). "
            "Use only real English. No duplicates."
        )
        data = await call_gemini_json(prompt, temperature=0.9, timeout=45.0)
        if isinstance(data, dict):
            data = data.get("items") or data.get("words") or []
        return data if isinstance(data, list) else []

    def _sanitize(
        self, raw: list, payload: PracticeSetGenerateRequest, context_key: str,
        known_keys: Set[str], user_id: UUID,
    ) -> List[dict]:
        rows: List[dict] = []
        seen: Set[str] = set(known_keys)
        sym = payload.phoneme if payload.kind == "phoneme" else None
        for item in raw:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()[:500]
            key = _norm(text)
            if not text or key in seen:
                continue
            target_type = str(item.get("target_type") or "word").strip().lower()
            if target_type not in ("word", "sentence"):
                target_type = "sentence" if len(text.split()) > 3 else "word"
            ipa_us = (str(item.get("ipa_us") or "").strip().strip("/").strip() or None)
            ipa_uk = (str(item.get("ipa_uk") or "").strip().strip("/").strip() or None)
            if sym and not ((ipa_us and sym in ipa_us) or (ipa_uk and sym in ipa_uk)):
                continue  # từ không chứa đúng âm mục tiêu
            seen.add(key)
            rows.append({
                "kind": payload.kind,
                "context_key": context_key,
                "text": text,
                "text_key": key,
                "target_type": target_type,
                "ipa_us": ipa_us[:500] if ipa_us else None,
                "ipa_uk": ipa_uk[:500] if ipa_uk else None,
                "hint": (str(item.get("hint") or "").strip()[:300] or None),
                "usage_count": 0,
                "created_by": user_id,
                "updated_by": user_id,
            })
        return rows[: payload.count]


pronunciation_practice_set_service = PronunciationPracticeSetService()
