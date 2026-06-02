import json
import logging
import os
import re
from typing import List, Dict, Any, Tuple

import requests
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.config import settings
from app.schemas.ai_schedule import AIAnalyzeRequest, AIAnalyzeResponse
from app.models.academic import Class, ClassEnrollment
from app.models.user import User

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

        if self.api_key:
            self.session = requests.Session()
        else:
            self.session = None
            logger.warning("GEMINI_API_KEY is not set. AIScheduleService will not work.")

    def _get_context_data(self, db: Session, text: str) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các lớp đang active và học viên trong lớp.
        Để tối ưu context, ta chỉ lấy các lớp/học viên có vẻ liên quan đến text.
        """
        text_lower = text.lower()
        
        # 1. Fetch active classes
        classes = db.query(Class).filter(
            Class.status == 'active', 
            Class.deleted_at.is_(None)
        ).all()
        
        # Filter classes that might be mentioned (simple heuristic: name overlap)
        # If the number of classes is small, we can just include all of them.
        # Let's include all active classes for now, as 100 classes is tiny for GPT-4.
        
        context_classes = []
        for c in classes:
            class_info = {
                "class_id": str(c.id),
                "class_name": c.name,
                "students": []
            }
            
            # Fetch students for this class
            enrollments = db.query(ClassEnrollment).filter(
                ClassEnrollment.class_id == c.id,
                ClassEnrollment.status == 'active',
                ClassEnrollment.deleted_at.is_(None)
            ).all()
            
            student_ids = [e.student_id for e in enrollments]
            
            if student_ids:
                students = db.query(User).filter(User.id.in_(student_ids)).all()
                for s in students:
                    full_name = f"{s.first_name} {s.last_name}"
                    # Only include student if their name appears in the text to save tokens
                    # or if the text is short, we could include all, but filtering is safer.
                    if s.first_name.lower() in text_lower or s.last_name.lower() in text_lower:
                        class_info["students"].append({
                            "student_id": str(s.id),
                            "name": full_name
                        })
            
            # Only add to context if the class name is in text, OR it has matched students.
            # (If text is just "An và Bình học cùng", we need the students to match).
            # To be safe, if a class has no matched students and its name isn't in the text, 
            # we can still include it but without the empty students list to save tokens.
            if class_info["students"]:
                context_classes.append(class_info)
            else:
                # Check if class name is somehow mentioned
                # Split class name into words to check
                class_words = c.name.lower().split()
                if any(w in text_lower for w in class_words if len(w) > 2): # basic filter
                    context_classes.append(class_info)
                elif len(context_classes) < 50: # If we don't have many, just include it just in case
                    context_classes.append(class_info)

        return context_classes

    def _generate_text(self, prompt: str) -> Dict[str, Any]:
        if not self.session:
            raise HTTPException(status_code=500, detail="Gemini API key is not configured.")

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

        response = self.session.post(endpoint, params=params, json=payload, headers=headers, timeout=30)
        if response.ok:
            return response.json()
        
        error_msg = f"{endpoint}: {response.status_code} - {response.text}"
        logger.error(f"Gemini request failed: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Gemini API request failed: {response.status_code}")

    def analyze_schedule_constraints(self, db: Session, request: AIAnalyzeRequest) -> AIAnalyzeResponse:
        if not self.session:
            raise HTTPException(status_code=500, detail="Gemini API key is not configured.")

        context_data = self._get_context_data(db, request.natural_language_text)
        
        system_prompt = f"""
Bạn là một trợ lý AI phân tích ngôn ngữ tự nhiên thành các tham số cho hệ thống Genetic Algorithm (GA) xếp thời khóa biểu.
Dưới đây là danh sách các lớp học đang mở và học viên (đã được lọc sơ bộ):
```json
{json.dumps(context_data, ensure_ascii=False, indent=2)}
```

Nhiệm vụ của bạn:
1. Đọc yêu cầu của người dùng.
2. Tìm ra các lớp học tương ứng (dựa vào tên lớp hoặc tên học viên học trong lớp đó).
3. Nếu yêu cầu xếp 2 (hoặc nhiều) lớp CÙNG MỘT BUỔI, hãy tạo ra cấu trúc `paired_class_ids`.
4. Nếu yêu cầu lớp học vào SÁNG/CHIỀU/TỐI, hãy tạo ra `class_preferences` với giá trị `morning` (sáng), `afternoon` (chiều), hoặc `evening` (tối).
5. Nếu yêu cầu có nhắc đến việc thay đổi mức độ ưu tiên (tuyệt đối không, hoặc rất quan trọng), hãy đề xuất `penalties_override` (ví dụ: penalty_paired_classes, penalty_consecutive_limit, penalty_time_preference). Trọng số từ 1 đến 50.
6. Trả về JSON đúng định dạng sau, KHÔNG giải thích lằng nhằng ngoài JSON:
{{
    "paired_class_ids": [["uuid_lop_1", "uuid_lop_2"]],
    "class_preferences": [{{"class_id": "uuid_lop", "preferred_time_period": "morning"}}],
    "penalties_override": {{"penalty_consecutive_limit": 10}},
    "ai_explanation": "Giải thích ngắn gọn bằng tiếng Việt lý do bạn chọn các tham số này.",
    "warnings": ["Cảnh báo nếu không tìm thấy học viên hoặc lớp được nhắc đến trong yêu cầu"]
}}
"""

        user_prompt = request.natural_language_text
        prompt = system_prompt + "\n\n" + user_prompt

        try:
            response_json = self._generate_text(prompt)
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

        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            raise HTTPException(status_code=500, detail=f"Lỗi khi gọi AI Gemini: {str(e)}")

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
