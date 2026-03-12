from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional

# Step 1: Import core components
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException
from app.dependencies import get_current_user, get_current_admin_user, CommonQueryParams

from app.services.chatbot_service import chatbot_service

# Step 1: Khai báo Router với ResponseWrapperRoute
router = APIRouter(tags=["Chatbot"], prefix="/chatbot", route_class=ResponseWrapperRoute)

# --- DTOs ---
class UserChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []

# --- ENDPOINTS ---

@router.post("/ask", response_model=ApiResponse[dict])
async def chat_with_ai(
    request: UserChatRequest,
    current_user = Depends(get_current_user)
):
    """
    API cho Frontend gọi để chat với AI.
    """
    real_role = current_user.role.value

    try:
        response = await chatbot_service.ask_bot(
            message=request.message,
            user_role=real_role,
            history=request.history
        )
        return ApiResponse(data=response)
    except Exception as e:
        raise APIException(
            status_code=500,
            code="CHAT_ERROR",
            message=f"An error occurred during chat: {str(e)}"
        )

@router.post("/admin/upload-doc", response_model=ApiResponse[dict])
async def upload_knowledge_base(
    file: UploadFile = File(...),
    current_user = Depends(get_current_admin_user)
):
    """
    API cho Admin upload tài liệu nội quy/giáo trình
    """
    try:
        result = await chatbot_service.upload_document(file)
        return ApiResponse(data=result)
    except Exception as e:
        raise APIException(
            status_code=400,
            code="UPLOAD_FAILED",
            message=f"Failed to upload knowledge base: {str(e)}"
        )