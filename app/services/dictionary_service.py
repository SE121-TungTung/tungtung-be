import httpx
import json
import re
import os
import logging
from sqlalchemy.orm import Session
from app.models.dictionary import DictionaryWord
from app.core.config import settings

logger = logging.getLogger(__name__)

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

        word_type = ""
        definition_en = ""
        example = ""
        
        if not data or not isinstance(data, list):
            # Fallback to AI lookup
            ai_data = await self._lookup_ai(word)
            if not ai_data:
                return None
                
            ipa = ai_data.get("ipa", "")
            word_type = ai_data.get("word_type", "")
            definition_en = ai_data.get("definition_en", "")
            example = ai_data.get("example_sentence", "")
            
        else:
            entry = data[0]
            
            # Bóc tách thông tin
            phonetics = entry.get("phonetics", [])
            for p in phonetics:
                if p.get("text"):
                    ipa = p["text"]
                    break
            
            meanings = entry.get("meanings", [])
            if meanings:
                first_meaning = meanings[0]
                word_type = first_meaning.get("partOfSpeech", "")
                definitions = first_meaning.get("definitions", [])
                if definitions:
                    definition_en = definitions[0].get("definition", "")
                    example = definitions[0].get("example", "")

        # Clean IPA (remove / / if Free Dictionary API includes them, to be consistent)
        if ipa.startswith("/") and ipa.endswith("/"):
            ipa = ipa[1:-1]
        
        # 3. Lưu xuống DB
        new_word = DictionaryWord(
            word=word,
            ipa=ipa,
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
            "word": new_word.word,
            "ipa": new_word.ipa,
            "word_type": new_word.word_type,
            "definition_en": new_word.definition_en,
            "example_sentence": new_word.example_sentence,
        }

    async def _lookup_ai(self, word: str) -> dict:
        api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None
            
        model_name = settings.GEMINI_MODEL
        if model_name in ("gemini-2.0-flash", "gemini-1.5-flash"):
            model_name = "gemini-2.5-flash"
            
        api_base_url = settings.GEMINI_API_URL.rstrip("/").replace("v1beta1", "v1beta")
        endpoint = f"{api_base_url}/models/{model_name}:generateContent"
        params = {"key": api_key}
        
        prompt = (
            f"You are an English dictionary API. Provide the dictionary definition for the word '{word}'. "
            "Return ONLY a raw JSON object (without markdown code blocks) with the following string keys: "
            "'word' (the word itself), "
            "'ipa' (the phonetic transcription without slashes), "
            "'word_type' (part of speech, e.g., 'noun', 'verb', 'adjective'), "
            "'definition_en' (a short, clear English definition), "
            "'example_sentence' (an example sentence using the word)."
        )
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(endpoint, params=params, json=payload, headers={"Content-Type": "application/json"}, timeout=15.0)
                if response.status_code != 200:
                    logger.warning(f"AI lookup failed: {response.text}")
                    return None
                    
                data = response.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return None
                    
                candidate = candidates[0]
                text_result = ""
                if "content" in candidate:
                    parts = candidate["content"].get("parts", [])
                    if parts and "text" in parts[0]:
                        text_result = parts[0]["text"]
                elif "output" in candidate:
                    text_result = candidate["output"]
                
                if not text_result:
                    return None
                    
                # Clean up json output
                text_result = text_result.strip()
                if text_result.startswith("```json"):
                    text_result = text_result[7:]
                if text_result.startswith("```"):
                    text_result = text_result[3:]
                if text_result.endswith("```"):
                    text_result = text_result[:-3]
                    
                return json.loads(text_result.strip())
        except Exception as e:
            logger.error(f"Error in AI dictionary lookup: {e}")
            return None

dictionary_service = DictionaryService()
