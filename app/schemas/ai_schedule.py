from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from uuid import UUID

from app.schemas.ga_schedule import GAClassPreference

class AIAnalyzeRequest(BaseModel):
    """Request gửi lên từ client để AI phân tích ràng buộc tự nhiên."""
    natural_language_text: str = Field(..., description="Câu yêu cầu bằng ngôn ngữ tự nhiên của admin")

class AIAnalyzeResponse(BaseModel):
    """Response trả về kết quả AI đã phân tích."""
    # List of UUID pairs: [[class1, class2], [class3, class4]]
    paired_class_ids: Optional[List[List[UUID]]] = Field(
        default=[], 
        description="Các cặp ID lớp học được ghép với nhau (cùng buổi)"
    )
    class_preferences: Optional[List[GAClassPreference]] = Field(
        default=[],
        description="Ca học ưu tiên của lớp (sáng/chiều/tối)"
    )
    penalties_override: Optional[Dict[str, float]] = Field(
        default=None,
        description="Điểm phạt cho các soft constraints, ví dụ: {'penalty_consecutive_limit': 10}"
    )
    # Lời giải thích của AI cho admin đọc
    ai_explanation: Optional[str] = Field(
        default=None, 
        description="Lời giải thích của AI về việc map các ràng buộc"
    )
    # Cảnh báo nếu AI phát hiện tên học viên/lớp không có trong context
    warnings: Optional[List[str]] = Field(
        default=[], 
        description="Cảnh báo nếu không tìm thấy dữ liệu khớp với text"
    )
    # Raw JSON output for debugging
    raw_response: Optional[Dict[str, Any]] = None
