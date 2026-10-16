"""
Gemini client dùng chung cho các tính năng Pronunciation (IPA, sinh bộ bài).
Mọi lỗi AI đều được quy về một thông báo thân thiện: "AI server đang lỗi, hãy thử lại sau".
"""
import asyncio
import json
import logging
import os
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import APIException

logger = logging.getLogger(__name__)

AI_ERROR_MESSAGE = "AI server đang lỗi, hãy thử lại sau."


def _ai_error(code: str = "AI_UNAVAILABLE", status_code: int = 503) -> APIException:
    return APIException(status_code=status_code, code=code, message=AI_ERROR_MESSAGE)


async def call_gemini_json(prompt: str, *, temperature: float = 0.4, timeout: float = 45.0) -> Any:
    """Gọi Gemini, trả về JSON đã parse. Raise APIException(503) khi lỗi/thiếu key."""
    api_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY is not configured")
        raise _ai_error("AI_NOT_CONFIGURED")

    # Danh sách model ứng viên theo thứ tự ưu tiên nếu model hiện tại dính rate limit (429) hoặc lỗi (503/404)
    candidate_models = [settings.GEMINI_MODEL, "gemini-flash-latest", "gemini-flash-lite-latest", "gemini-3.8-flash", "gemini-2.5-flash"]
    # Loại bỏ duplicate giữ nguyên thứ tự
    models_to_try = []
    for m in candidate_models:
        if m and m not in models_to_try:
            models_to_try.append(m)

    base = settings.GEMINI_API_URL.rstrip("/").replace("v1beta1", "v1beta")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }

    last_resp = None
    for model_name in models_to_try:
        endpoint = f"{base}/models/{model_name}:generateContent"
        for attempt in range(2):
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(endpoint, params={"key": api_key}, json=payload, timeout=timeout)
                    last_resp = resp
            except httpx.HTTPError as e:
                logger.error("Gemini connection error with model %s: %s", model_name, e)
                last_resp = None
                await asyncio.sleep(0.5)
                continue

            if resp is not None and resp.status_code == 200:
                try:
                    data = resp.json()
                    text_result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if text_result.startswith("```"):
                        text_result = text_result.strip("`")
                        if text_result.lower().startswith("json"):
                            text_result = text_result[4:]
                    return json.loads(text_result.strip())
                except (KeyError, IndexError, ValueError) as e:
                    logger.error("Gemini parse error with %s: %s", model_name, e)
                    break

            if resp is not None and resp.status_code in (429, 404, 500, 503):
                logger.warning("Gemini model %s returned status %s, attempting next candidate...", model_name, resp.status_code)
                break  # Chuyển ngay sang candidate model tiếp theo

    if last_resp is not None and last_resp.status_code != 200:
        logger.error("All Gemini candidate models failed. Last status %s: %s", last_resp.status_code, last_resp.text[:300])
    raise _ai_error("AI_FAILED")

