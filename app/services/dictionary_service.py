import httpx
import json
import re
import os
import logging
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.dictionary import DictionaryWord
from app.core.config import settings
from app.core.exceptions import APIException
from app.services.gemini_client import call_gemini_json

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-zA-Z]+(?:['\-][a-zA-Z]+)*")
MAX_TEXTS = 20
MAX_TOKENS_PER_TEXT = 40


def _clean_ipa(value: Optional[str]) -> Optional[str]:
    """Bỏ dấu / / bao quanh; trả None nếu rỗng."""
    if not value:
        return None
    v = str(value).strip().strip("/").strip()
    return v or None


class DictionaryService:
    async def lookup_word(self, db: Session, word: str) -> dict:
        word = word.strip().lower()
        if not word:
            return None

        # 1. Tra trong DB cache
        existing = db.query(DictionaryWord).filter(DictionaryWord.word == word).first()
        if existing:
            return {
                "word": existing.word,
                "ipa": existing.ipa,
                "ipa_us": existing.ipa_us or existing.ipa,
                "ipa_uk": existing.ipa_uk or existing.ipa,
                "word_type": existing.word_type,
                "definition_en": existing.definition_en,
                "example_sentence": existing.example_sentence,
            }

        # 2. Gọi API nếu chưa có
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        data = None
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=5.0)
                if response.status_code == 200:
                    data = response.json()
        except Exception as e:
            logger.warning(f"Free dictionary API error: {e}")

        ipa = ""
        ipa_us: Optional[str] = None
        ipa_uk: Optional[str] = None
        word_type = ""
        definition_en = ""
        example = ""
        
        if not data or not isinstance(data, list):
            # Fallback to AI lookup
            ai_data = await self._lookup_ai(word)
            if not ai_data:
                return None
                
            ipa = ai_data.get("ipa", "") or ""
            ipa_us = _clean_ipa(ai_data.get("ipa_us"))
            ipa_uk = _clean_ipa(ai_data.get("ipa_uk"))
            word_type = ai_data.get("word_type", "")
            definition_en = ai_data.get("definition_en", "")
            example = ai_data.get("example_sentence", "")
            
        else:
            entry = data[0]
            
            # Bóc tách thông tin
            ipa_us, ipa_uk, ipa = self._parse_phonetics(entry.get("phonetics", []))
            ipa = ipa or ""
            
            meanings = entry.get("meanings", [])
            if meanings:
                first_meaning = meanings[0]
                word_type = first_meaning.get("partOfSpeech", "")
                definitions = first_meaning.get("definitions", [])
                if definitions:
                    definition_en = definitions[0].get("definition", "")
                    example = definitions[0].get("example", "")

        # Clean IPA (remove / / if Free Dictionary API includes them, to be consistent)
        ipa = _clean_ipa(ipa) or ""

        # Bù US/UK còn thiếu bằng AI (dict API thường chỉ có 1 phiên âm chung)
        if not ipa_us or not ipa_uk:
            ai_ipa = await self._ai_ipa_for_words([word])
            pair = ai_ipa.get(word)
            if pair:
                ipa_us = ipa_us or pair[0]
                ipa_uk = ipa_uk or pair[1]
        ipa_us = ipa_us or _clean_ipa(ipa)
        ipa_uk = ipa_uk or _clean_ipa(ipa)
        ipa = ipa or ipa_us or ipa_uk or ""
        
        # 3. Lưu xuống DB
        new_word = DictionaryWord(
            word=word,
            ipa=ipa,
            ipa_us=ipa_us,
            ipa_uk=ipa_uk,
            word_type=word_type,
            definition_en=definition_en,
            example_sentence=example,
            created_by=None,
            updated_by=None,
        )
        try:
            db.add(new_word)
            db.commit()
            db.refresh(new_word)
        except Exception:
            db.rollback()

        return {
            "word": word,
            "ipa": ipa,
            "ipa_us": ipa_us,
            "ipa_uk": ipa_uk,
            "word_type": word_type,
            "definition_en": definition_en,
            "example_sentence": example,
        }

    # ------------------------------------------------------------------
    # IPA US / UK
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_phonetics(phonetics: list) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Từ phonetics của Free Dictionary API -> (us, uk, generic). Phân giọng theo hậu tố audio."""
        us = uk = generic = None
        for p in phonetics or []:
            text = _clean_ipa(p.get("text"))
            if not text:
                continue
            audio = (p.get("audio") or "").lower()
            if audio.endswith("-us.mp3") or "-us." in audio:
                us = us or text
            elif audio.endswith("-uk.mp3") or "-uk." in audio or "-au." in audio:
                uk = uk or text
            else:
                generic = generic or text
        return us, uk, generic

    async def lookup_ipa_batch(self, db: Session, texts: List[str]) -> List[dict]:
        """
        Tra IPA US/UK cho nhiều từ/câu. Thứ tự: cache DB -> Free Dictionary API -> Gemini.
        Không bao giờ trả lại chính chữ làm IPA; không tìm được thì ipa_us/ipa_uk = None.
        """
        texts = [t for t in (texts or [])][:MAX_TEXTS]
        tokenized: List[List[str]] = []
        all_words: List[str] = []
        for t in texts:
            tokens = [m.group(0).lower() for m in _TOKEN_RE.finditer(t or "")][:MAX_TOKENS_PER_TEXT]
            tokenized.append(tokens)
            for w in tokens:
                if w not in all_words:
                    all_words.append(w)

        word_ipa = await self._resolve_words(db, all_words)

        results: List[dict] = []
        for text, tokens in zip(texts, tokenized):
            if not tokens:
                results.append({"text": text, "ipa_us": None, "ipa_uk": None, "source": "none"})
                continue
            us_parts = [word_ipa.get(w, (None, None, ""))[0] for w in tokens]
            uk_parts = [word_ipa.get(w, (None, None, ""))[1] for w in tokens]
            if all(us_parts) and all(uk_parts):
                src = "cache" if all(word_ipa[w][2] == "cache" for w in tokens) else "dictionary"
                if any(word_ipa[w][2] == "ai" for w in tokens):
                    src = "ai"
                results.append({
                    "text": text,
                    "ipa_us": " ".join(us_parts),
                    "ipa_uk": " ".join(uk_parts),
                    "source": src,
                })
            else:
                results.append({"text": text, "ipa_us": None, "ipa_uk": None, "source": "none"})
        return results

    async def _resolve_words(
        self, db: Session, words: List[str]
    ) -> Dict[str, Tuple[Optional[str], Optional[str], str]]:
        """Trả {word: (us, uk, source)} cho các từ tra được; ghi cache DB."""
        out: Dict[str, Tuple[Optional[str], Optional[str], str]] = {}
        if not words:
            return out

        rows = db.query(DictionaryWord).filter(DictionaryWord.word.in_(words)).all()
        row_map = {r.word: r for r in rows}
        need_ai: List[str] = []
        pending: Dict[str, dict] = {}  # từ cần tra dict API / AI

        for w in words:
            row = row_map.get(w)
            if row and row.ipa_us and row.ipa_uk:
                out[w] = (row.ipa_us, row.ipa_uk, "cache")
            else:
                pending[w] = {"row": row}

        # Free Dictionary API cho từ chưa có đủ US/UK
        for w, ctx in pending.items():
            us = uk = generic = None
            row = ctx["row"]
            if row:
                us, uk, generic = row.ipa_us, row.ipa_uk, _clean_ipa(row.ipa)
            else:
                try:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}", timeout=5.0
                        )
                    if resp.status_code == 200:
                        entry = resp.json()[0]
                        us, uk, generic = self._parse_phonetics(entry.get("phonetics", []))
                        ctx["entry"] = entry
                except Exception as e:
                    logger.warning(f"Free dictionary API error for '{w}': {e}")
            ctx.update(us=us, uk=uk, generic=generic)
            if not (us and uk):
                need_ai.append(w)

        ai_map: Dict[str, Tuple[str, str]] = {}
        if need_ai:
            ai_map = await self._ai_ipa_for_words(need_ai)

        for w, ctx in pending.items():
            us, uk, generic = ctx["us"], ctx["uk"], ctx["generic"]
            source = "dictionary"
            pair = ai_map.get(w)
            if pair:
                if not us or not uk:
                    source = "ai"
                us = us or pair[0]
                uk = uk or pair[1]
            # Không phân biệt được giọng -> dùng phiên âm chung của dict API
            us = us or generic
            uk = uk or generic
            if not (us or uk):
                continue
            out[w] = (us, uk, source)
            self._save_word_ipa(db, w, ctx, us, uk, generic)
        return out

    @staticmethod
    def _save_word_ipa(db: Session, word: str, ctx: dict, us: Optional[str], uk: Optional[str], generic: Optional[str]) -> None:
        try:
            row = ctx.get("row")
            if row:
                row.ipa_us = us
                row.ipa_uk = uk
                row.ipa = row.ipa or generic or us or uk
            else:
                entry = ctx.get("entry") or {}
                word_type = ""
                definition_en = ""
                example = ""
                meanings = entry.get("meanings") or []
                if meanings:
                    word_type = meanings[0].get("partOfSpeech", "")
                    defs = meanings[0].get("definitions") or []
                    if defs:
                        definition_en = defs[0].get("definition", "")
                        example = defs[0].get("example", "")
                db.add(DictionaryWord(
                    word=word, ipa=generic or us or uk, ipa_us=us, ipa_uk=uk,
                    word_type=word_type, definition_en=definition_en,
                    example_sentence=example, created_by=None, updated_by=None,
                ))
            db.commit()
        except Exception:
            db.rollback()

    async def _ai_ipa_for_words(self, words: List[str]) -> Dict[str, Tuple[str, str]]:
        """Gemini: IPA GenAm (US) và RP (UK) cho danh sách từ. Lỗi AI -> {} (IPA là thông tin phụ)."""
        if not words:
            return {}
        prompt = (
            "You are a phonetics expert. For each English word below give the IPA transcription "
            "for American English (General American) and British English (Received Pronunciation). "
            "Use standard IPA symbols WITHOUT surrounding slashes. "
            "Return ONLY a raw JSON object mapping each given word (lowercase) to "
            "{\"us\": \"...\", \"uk\": \"...\"}. Skip words that are not real English words.\n\n"
            "WORDS:\n" + "\n".join(f"- {w}" for w in words)
        )
        try:
            data = await call_gemini_json(prompt, temperature=0.1, timeout=30.0)
        except APIException:
            return {}
        result: Dict[str, Tuple[str, str]] = {}
        if isinstance(data, dict):
            for w in words:
                item = data.get(w) or data.get(w.capitalize())
                if isinstance(item, dict):
                    us = _clean_ipa(item.get("us"))
                    uk = _clean_ipa(item.get("uk"))
                    if us and uk:
                        result[w] = (us, uk)
        return result

    async def _lookup_ai(self, word: str) -> dict:
        prompt = (
            f"You are an English dictionary API. Provide the dictionary definition for the word '{word}'. "
            "Return ONLY a raw JSON object (without markdown code blocks) with the following string keys: "
            "'word' (the word itself), "
            "'ipa' (the phonetic transcription without slashes), "
            "'ipa_us' (American IPA without slashes), "
            "'ipa_uk' (British IPA without slashes), "
            "'word_type' (part of speech, e.g., 'noun', 'verb', 'adjective'), "
            "'definition_en' (a short, clear English definition), "
            "'example_sentence' (an example sentence using the word)."
        )
        try:
            parsed = await call_gemini_json(prompt, temperature=0.1, timeout=15.0)
            if isinstance(parsed, dict) and "word" in parsed:
                return parsed
        except Exception as e:
            logger.warning(f"AI lookup failed for word {word}: {e}")
        return None

dictionary_service = DictionaryService()
