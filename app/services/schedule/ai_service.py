import json
import logging
import os
import re
from typing import List, Dict, Any, Tuple

import httpx

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AIConfigurationException, AIRequestException
from app.schemas.ai_schedule import AIAnalyzeRequest, AIAnalyzeResponse
from app.services.schedule.ai_prompts import get_system_prompt
from app.repositories.class_repository import class_repository

logger = logging.getLogger(__name__)

class AIScheduleService:
    def __init__(self):
        self.api_key = (
            settings.GEMINI_API_KEY
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        self.model_name = settings.GEMINI_MODEL
        # gemini-2.0-flash is deprecated and 1.5-flash is retired. Fallback to gemini-2.5-flash
        if self.model_name in ("gemini-2.0-flash", "gemini-1.5-flash"):
            self.model_name = "gemini-2.5-flash"
            
        self.api_base_url = settings.GEMINI_API_URL

        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. AIScheduleService will not work.")

    def _get_context_data(self, db: Session, text: str) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các lớp đang active và học viên trong lớp bằng ClassRepository.
        Để tối ưu context, ta chỉ lấy các lớp/học viên có vẻ liên quan đến text.
        """
        text_lower = text.lower()
        
        # Fetch active classes using repository
        classes = class_repository.get_active_classes_with_students(db)
        
        context_classes = []
        for c in classes:
            class_info = {
                "class_id": str(c.id),
                "class_name": c.name,
                "students": []
            }
            
            # Fetch students from eager-loaded enrollments
            for enrollment in c.enrollments:
                if enrollment.status != 'active' or enrollment.deleted_at is not None:
                    continue
                
                s = enrollment.student
                if not s or s.deleted_at is not None:
                    continue
                
                full_name = f"{s.first_name} {s.last_name}"
                if s.first_name.lower() in text_lower or s.last_name.lower() in text_lower:
                    class_info["students"].append({
                        "student_id": str(s.id),
                        "name": full_name
                    })
            
            # Only add to context if the class name is in text, OR it has matched students.
            if class_info["students"]:
                context_classes.append(class_info)
            else:
                # Check if class name is somehow mentioned
                class_words = c.name.lower().split()
                if any(w in text_lower for w in class_words if len(w) > 2): # basic filter
                    context_classes.append(class_info)
                elif len(context_classes) < 50: # If we don't have many, just include it just in case
                    context_classes.append(class_info)

        return context_classes

    async def _generate_text(self, prompt: str) -> Dict[str, Any]:
        if not self.api_key:
            raise AIConfigurationException(message="Gemini API key is not configured.")

        # Ensure we use v1beta for Gemini models instead of the deprecated v1beta1
        # Also strip any trailing slashes to prevent 404 from double slashes in URL
        api_base_url = self.api_base_url.rstrip("/").replace("v1beta1", "v1beta")
        endpoint = f"{api_base_url}/models/{self.model_name}:generateContent"
        params = {"key": self.api_key}
        
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }
        headers = {"Content-Type": "application/json"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(endpoint, params=params, json=payload, headers=headers, timeout=30.0)
                if response.status_code == 200:
                    return response.json()
            except httpx.RequestError as e:
                logger.error(f"Gemini connection error: {e}")
                raise AIRequestException(message=f"Không thể kết nối tới AI Service: {e}", status_code=503)
        
        error_msg = f"{endpoint}: {response.status_code} - {response.text}"
        logger.error(f"Gemini request failed: {error_msg}")
        raise AIRequestException(message=f"Gemini API request failed: {response.status_code}")

    async def analyze_schedule_constraints(self, db: Session, request: AIAnalyzeRequest) -> AIAnalyzeResponse:
        if not self.api_key:
            raise AIConfigurationException(message="Gemini API key is not configured.")

        context_data = self._get_context_data(db, request.natural_language_text)
        
        # Load system prompt template from decoupled module
        system_prompt = get_system_prompt(context_data)
        user_prompt = request.natural_language_text
        prompt = system_prompt + "\n\n" + user_prompt

        try:
            response_json = await self._generate_text(prompt)
            result_text = self._extract_text(response_json)

            try:
                result_json = json.loads(result_text)
            except json.JSONDecodeError:
                json_match = re.search(r"(\{.*\})", result_text, re.DOTALL)
                if not json_match:
                    raise
                result_json = json.loads(json_match.group(1))

            return AIAnalyzeResponse(
                paired_class_ids=result_json.get("paired_class_ids", []),
                class_preferences=result_json.get("class_preferences", []),
                penalties_override=result_json.get("penalties_override", None),
                ai_explanation=result_json.get("ai_explanation", ""),
                warnings=result_json.get("warnings", []),
                raw_response=result_json
            )

        except AIServiceException:
            # Re-raise domain-specific exceptions directly
            raise
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            raise AIServiceException(message=f"Lỗi khi gọi AI Gemini: {str(e)}")

    def _extract_text(self, response_json: Dict[str, Any]) -> str:
        candidates = response_json.get("candidates") or []
        if not candidates:
            raise ValueError("Gemini response did not return any candidates")

        candidate = candidates[0]
        if isinstance(candidate, dict):
            # Handle generateContent response: candidate.content.parts[0].text
            if "content" in candidate:
                content = candidate["content"]
                if isinstance(content, dict):
                    parts = content.get("parts") or []
                    if parts and isinstance(parts[0], dict):
                        if "text" in parts[0]:
                            return parts[0]["text"]
                elif isinstance(content, str):
                    return content
            # Handle legacy response: candidate.output
            if "output" in candidate:
                return candidate["output"]
        
        # Fallback: check top-level output
        if "output" in response_json and isinstance(response_json["output"], str):
            return response_json["output"]

        raise ValueError(f"Unable to extract text from Gemini response: {json.dumps(response_json)[:200]}")

ai_schedule_service = AIScheduleService()
