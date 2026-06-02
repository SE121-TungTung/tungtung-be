from fastapi import APIRouter, Depends, UploadFile, File, Form
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from uuid import UUID

# Step 1: Import core components
from app.core.database import get_db
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException
from app.dependencies import get_current_user, get_current_admin_user, CommonQueryParams

from app.services.chatbot_service import chatbot_service
from app.models.chatbot_document import ChatbotDocument, DocCategory
from app.schemas.chatbot import ChatbotDocumentResponse

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

@router.post("/admin/upload-doc", response_model=ApiResponse[ChatbotDocumentResponse])
async def upload_knowledge_base(
    file: UploadFile = File(...),
    doc_category: str = Form("business"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    API cho Admin upload tài liệu nội quy/giáo trình
    """
    try:
        # Forward file sang Chatbot Service
        result = await chatbot_service.upload_document(file, doc_category)
        doc_id_from_chatbot = result.get("doc_id")
        
        if not doc_id_from_chatbot:
            raise Exception("AI Server did not return a doc_id")
            
        # Lưu vào PostgreSQL
        new_doc = ChatbotDocument(
            doc_id=doc_id_from_chatbot,
            filename=file.filename,
            category=DocCategory(doc_category),
            uploaded_by=current_user.id
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        
        # Populate additional fields for response
        new_doc.uploaded_by_name = f"{current_user.first_name} {current_user.last_name}"
        
        return ApiResponse(data=ChatbotDocumentResponse.model_validate(new_doc, from_attributes=True))
    except Exception as e:
        db.rollback()
        raise APIException(
            status_code=400,
            code="UPLOAD_FAILED",
            message=f"Failed to upload knowledge base: {str(e)}"
        )

@router.get("/admin/documents", response_model=PaginationResponse[ChatbotDocumentResponse])
async def list_documents(
    commons: CommonQueryParams = Depends(),
    category: Optional[DocCategory] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    Lấy danh sách tài liệu Chatbot từ Database
    """
    from app.models.user import User
    
    query = db.query(ChatbotDocument, User).join(User, ChatbotDocument.uploaded_by == User.id)
    
    if category:
        query = query.filter(ChatbotDocument.category == category)
        
    total = query.count()
    items = query.order_by(ChatbotDocument.created_at.desc()).offset(commons.skip).limit(commons.limit).all()
    
    # Map to schema
    results = []
    for doc, user in items:
        doc.uploaded_by_name = f"{user.first_name} {user.last_name}"
        results.append(ChatbotDocumentResponse.model_validate(doc, from_attributes=True))
        
    return PaginationResponse(
        data=results,
        total=total,
        page=commons.page,
        limit=commons.limit
    )

@router.delete("/admin/documents/{doc_id}", response_model=ApiResponse[str])
async def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    Xóa tài liệu Chatbot
    """
    doc = db.query(ChatbotDocument).filter(ChatbotDocument.doc_id == doc_id).first()
    if not doc:
        raise APIException(
            status_code=404,
            code="DOC_NOT_FOUND",
            message="Document not found in database"
        )
        
    try:
        # Xóa trên AI Server
        await chatbot_service.delete_document(doc_id)
        
        # Xóa trên Database
        db.delete(doc)
        db.commit()
        return ApiResponse(data="Document deleted successfully")
    except Exception as e:
        db.rollback()
        raise APIException(
            status_code=500,
            code="DELETE_FAILED",
            message=f"Failed to delete document: {str(e)}"
        )

@router.put("/admin/documents/{doc_id}", response_model=ApiResponse[ChatbotDocumentResponse])
async def update_document(
    doc_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    Thay thế file của tài liệu Chatbot hiện tại
    """
    doc = db.query(ChatbotDocument).filter(ChatbotDocument.doc_id == doc_id).first()
    if not doc:
        raise APIException(
            status_code=404,
            code="DOC_NOT_FOUND",
            message="Document not found in database"
        )
        
    try:
        # Xóa trên AI Server
        await chatbot_service.delete_document(doc_id)
        
        # Upload mới
        result = await chatbot_service.upload_document(file, doc.category.value)
        new_doc_id_from_chatbot = result.get("doc_id")
        
        if not new_doc_id_from_chatbot:
            raise Exception("AI Server did not return a new doc_id")
            
        # Cập nhật Database
        doc.doc_id = new_doc_id_from_chatbot
        doc.filename = file.filename
        doc.uploaded_by = current_user.id
        
        db.commit()
        db.refresh(doc)
        
        doc.uploaded_by_name = f"{current_user.first_name} {current_user.last_name}"
        
        return ApiResponse(data=ChatbotDocumentResponse.model_validate(doc, from_attributes=True))
    except Exception as e:
        db.rollback()
        raise APIException(
            status_code=500,
            code="UPDATE_FAILED",
            message=f"Failed to update document: {str(e)}"
        )