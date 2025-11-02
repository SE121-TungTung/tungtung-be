from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional, List, Dict, Any

# --- Input: Bắt đầu làm bài ---
class TestAttemptStart(BaseModel):
    test_id: UUID
    student_id: UUID = Field(..., description="ID của học sinh đang làm bài.")
    # Có thể thêm: ip_address, user_agent (Nếu không lấy tự động từ Request)

# --- Input: Lưu câu trả lời/Phản hồi ---
class TestResponseCreate(BaseModel):
    question_id: UUID
    response_text: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None # Dữ liệu phức tạp (JSONB)
    time_spent_seconds: Optional[int] = Field(None, ge=0)
    flagged_for_review: Optional[bool] = False
    
# --- Input: Nộp bài (Submit) ---
class TestAttemptSubmit(BaseModel):
    # Chỉ cần ID của Attempt để submit
    pass