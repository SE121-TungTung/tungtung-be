from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from uuid import UUID
import logging

# Step 1: Import core components
from app.core.database import get_db, SessionLocal
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException
from app.dependencies import get_current_user, get_current_admin_user, CommonQueryParams

from app.services.chatbot_service import chatbot_service
from app.models.chatbot_document import ChatbotDocument, DocCategory, DocStatus
from app.schemas.chatbot import ChatbotDocumentResponse

logger = logging.getLogger(__name__)

# Step 1: Khai báo Router với ResponseWrapperRoute
router = APIRouter(tags=["Chatbot"], prefix="/chatbot", route_class=ResponseWrapperRoute)

# --- DTOs ---
class UserChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []

# --- Background task for uploading to AI server ---
async def _process_upload_to_ai(doc_db_id: UUID, file_content: bytes, filename: str, content_type: str, doc_category: str, user_id: UUID):
    """
    Background task: upload file to AI server, then update DB record status.
    Also sends a notification to the user.
    """
    db = SessionLocal()
    try:
        doc = db.query(ChatbotDocument).filter(ChatbotDocument.id == doc_db_id).first()
        if not doc:
            logger.error(f"Document {doc_db_id} not found in DB for background processing")
            return

        # Create a pseudo-UploadFile for the service
        import io
        from starlette.datastructures import UploadFile as StarletteUploadFile

        file_like = io.BytesIO(file_content)
        pseudo_file = StarletteUploadFile(filename=filename, file=file_like, headers={"content-type": content_type or "application/octet-stream"})

        try:
            result = await chatbot_service.upload_document(pseudo_file, doc_category)
            doc_id_from_chatbot = result.get("doc_id")

            if not doc_id_from_chatbot:
                raise Exception("AI Server did not return a doc_id")

            doc.doc_id = doc_id_from_chatbot
            doc.status = DocStatus.completed
            doc.error_message = None
            db.commit()

            # Send success notification
            from app.services.notification_service import notification_service
            from app.schemas.notification import NotificationCreate
            from app.models.notification import NotificationType, NotificationPriority

            noti = NotificationCreate(
                user_id=user_id,
                title="Tải tài liệu thành công",
                content=f"Tài liệu \"{filename}\" đã được tải lên và Chatbot đã học kiến thức mới.",
                notification_type=NotificationType.SYSTEM_ALERT,
                priority=NotificationPriority.NORMAL,
                action_url="/admin/system/chatbot-documents",
                channels=["in_app"],
            )
            await notification_service.send_notification(db=db, noti_info=noti)
            logger.info(f"Document {filename} uploaded successfully, doc_id={doc_id_from_chatbot}")

        except Exception as upload_err:
            error_msg = str(upload_err)
            logger.error(f"Background upload failed for {filename}: {error_msg}")
            doc.status = DocStatus.failed
            doc.error_message = error_msg[:500]  # Truncate long errors
            db.commit()

            # Send failure notification
            try:
                from app.services.notification_service import notification_service
                from app.schemas.notification import NotificationCreate
                from app.models.notification import NotificationType, NotificationPriority

                noti = NotificationCreate(
                    user_id=user_id,
                    title="Tải tài liệu thất bại",
                    content=f"Tài liệu \"{filename}\" không thể tải lên AI Server. Vui lòng thử lại.",
                    notification_type=NotificationType.SYSTEM_ALERT,
                    priority=NotificationPriority.HIGH,
                    action_url="/admin/system/chatbot-documents",
                    channels=["in_app"],
                )
                await notification_service.send_notification(db=db, noti_info=noti)
            except Exception as noti_err:
                logger.error(f"Failed to send failure notification: {noti_err}")

    except Exception as e:
        logger.error(f"Critical error in background upload: {e}")
    finally:
        db.close()


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

@router.post("/ask/stream")
async def chat_with_ai_stream(
    request: UserChatRequest,
    current_user = Depends(get_current_user)
):
    """
    API cho Frontend gọi để chat stream với AI.
    """
    real_role = current_user.role.value
    
    try:
        stream_gen = await chatbot_service.ask_bot_stream(
            message=request.message,
            user_role=real_role,
            history=request.history
        )
        
        import json
        async def sse_wrapper():
            async for chunk in stream_gen:
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"

        return StreamingResponse(sse_wrapper(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Error in chat stream: {e}")
        raise APIException(
            status_code=500,
            code="CHAT_STREAM_ERROR",
            message=f"An error occurred during chat stream: {str(e)}"
        )

@router.post("/admin/upload-doc", response_model=ApiResponse[ChatbotDocumentResponse])
async def upload_knowledge_base(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_category: str = Form("business"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    API cho Admin upload tài liệu nội quy/giáo trình.
    Trả về ngay lập tức với status=processing, upload AI chạy nền.
    """
    try:
        # Read file content upfront (before response returns)
        file_content = await file.read()

        # Create DB record immediately with status=processing
        new_doc = ChatbotDocument(
            doc_id=None,  # Will be filled by background task
            filename=file.filename,
            category=DocCategory(doc_category),
            status=DocStatus.processing,
            created_by=current_user.id
        )
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)

        # Schedule background upload
        background_tasks.add_task(
            _process_upload_to_ai,
            doc_db_id=new_doc.id,
            file_content=file_content,
            filename=file.filename,
            content_type=file.content_type,
            doc_category=doc_category,
            user_id=current_user.id,
        )

        # Return immediately with processing status
        new_doc.uploaded_by_name = f"{current_user.first_name} {current_user.last_name}"

        return ApiResponse(data=ChatbotDocumentResponse.model_validate(new_doc, from_attributes=True))
    except Exception as e:
        db.rollback()
        raise APIException(
            status_code=400,
            code="UPLOAD_FAILED",
            message=f"Failed to initiate upload: {str(e)}"
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
    
    query = db.query(ChatbotDocument, User).join(User, ChatbotDocument.created_by == User.id)
    
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

@router.get("/admin/documents/{doc_db_id}/status", response_model=ApiResponse[ChatbotDocumentResponse])
async def get_document_status(
    doc_db_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    Polling endpoint: check status of a specific document upload.
    """
    from app.models.user import User
    
    result = db.query(ChatbotDocument, User).join(
        User, ChatbotDocument.created_by == User.id
    ).filter(ChatbotDocument.id == doc_db_id).first()
    
    if not result:
        raise APIException(status_code=404, code="DOC_NOT_FOUND", message="Document not found")
    
    doc, user = result
    doc.uploaded_by_name = f"{user.first_name} {user.last_name}"
    return ApiResponse(data=ChatbotDocumentResponse.model_validate(doc, from_attributes=True))

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
        # Also try matching by id (UUID) for processing docs without doc_id
        doc = db.query(ChatbotDocument).filter(ChatbotDocument.id == doc_id).first()
    
    if not doc:
        raise APIException(
            status_code=404,
            code="DOC_NOT_FOUND",
            message="Document not found in database"
        )
        
    try:
        # Only delete from AI server if document was completed
        if doc.doc_id and doc.status == DocStatus.completed:
            try:
                await chatbot_service.delete_document(doc.doc_id)
            except HTTPException as he:
                if he.status_code == 404:
                    logger.warning(f"Document {doc.doc_id} not found on AI server (404), proceeding with database deletion.")
                else:
                    raise he
        
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

@router.post("/admin/documents/{doc_db_id}/retry", response_model=ApiResponse[ChatbotDocumentResponse])
async def retry_upload(
    doc_db_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    Retry a failed upload by providing a new file.
    """
    doc = db.query(ChatbotDocument).filter(ChatbotDocument.id == doc_db_id).first()
    if not doc:
        raise APIException(status_code=404, code="DOC_NOT_FOUND", message="Document not found")
    
    if doc.status not in (DocStatus.failed,):
        raise APIException(status_code=400, code="INVALID_STATUS", message="Only failed documents can be retried")
    
    file_content = await file.read()
    
    # Reset status
    doc.status = DocStatus.processing
    doc.error_message = None
    doc.filename = file.filename
    db.commit()
    db.refresh(doc)
    
    background_tasks.add_task(
        _process_upload_to_ai,
        doc_db_id=doc.id,
        file_content=file_content,
        filename=file.filename,
        content_type=file.content_type,
        doc_category=doc.category.value,
        user_id=current_user.id,
    )
    
    from app.models.user import User
    user = db.query(User).filter(User.id == doc.created_by).first()
    doc.uploaded_by_name = f"{user.first_name} {user.last_name}" if user else ""
    
    return ApiResponse(data=ChatbotDocumentResponse.model_validate(doc, from_attributes=True))

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
        try:
            await chatbot_service.delete_document(doc_id)
        except HTTPException as he:
            if he.status_code == 404:
                logger.warning(f"Document {doc_id} not found on AI server for update (404), proceeding with new upload.")
            else:
                raise he
        
        # Upload mới
        result = await chatbot_service.upload_document(file, doc.category.value)
        new_doc_id_from_chatbot = result.get("doc_id")
        
        if not new_doc_id_from_chatbot:
            raise Exception("AI Server did not return a new doc_id")
            
        # Cập nhật Database
        doc.doc_id = new_doc_id_from_chatbot
        doc.filename = file.filename
        doc.created_by = current_user.id
        
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