from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
from app.services.chatbot import chatbot_service
from app.dependencies import get_current_user, get_current_admin_user

router = APIRouter()

# --- DTOs ---
class UserChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []

# --- ENDPOINTS ---

@router.post("/ask")
async def chat_with_ai(
    request: UserChatRequest,
    current_user = Depends(get_current_user)
):
    """
    API cho Frontend gọi để chat với AI.
    """
    real_role = current_user.role.value

    response = await chatbot_service.ask_bot(
        message=request.message,
        user_role=real_role,
        history=request.history
    )

    # (Tuỳ chọn) Lưu log chat vào Database chính
    # await save_chat_log(user_id=current_user.id, msg=request.message, reply=response['reply'])

    return response

@router.post("/admin/upload-doc")
async def upload_knowledge_base(
    file: UploadFile = File(...),
    current_user = Depends(get_current_admin_user)
):
    """
    API cho Admin upload tài liệu nội quy/giáo trình
    """
    return await chatbot_service.upload_document(file)