import json
from typing import List, Dict, Any

def get_system_prompt(context_data: List[Dict[str, Any]]) -> str:
    """
    Generate the system prompt for the Gemini LLM with context details of active classes and students.
    """
    context_json = json.dumps(context_data, ensure_ascii=False, indent=2)
    return f"""Bạn là một trợ lý AI phân tích ngôn ngữ tự nhiên thành các tham số cho hệ thống Genetic Algorithm (GA) xếp thời khóa biểu.
Dưới đây là danh sách các lớp học đang mở và học viên (đã được lọc sơ bộ):
```json
{context_json}
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
}}"""
