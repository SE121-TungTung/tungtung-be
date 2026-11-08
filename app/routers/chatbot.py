from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from uuid import UUID
import logging
import json

# Step 1: Import core components
from app.core.database import get_db, SessionLocal
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException
from app.dependencies import get_current_user, get_current_user_optional, get_current_admin_user, CommonQueryParams

from app.services.chatbot_service import chatbot_service, normalize_audience
from app.services.audit_log_service import audit_service
from app.models.audit_log import AuditAction
from app.models.chatbot_document import ChatbotDocument, DocCategory, DocStatus, DEFAULT_DOCUMENT_AUDIENCE
from app.schemas.chatbot import (
    ChatbotDocumentResponse,
    ChatbotDocumentAudienceUpdate,
    ChatbotDocumentBulkAudienceUpdate,
)

logger = logging.getLogger(__name__)

_schema_migrated = False


def _ensure_chatbot_documents_schema(db: Session):
    """
    Migration tự động cho bảng chatbot_documents:
      - Thêm cột audience (mặc định ['student', 'teacher', 'staff', 'admin'])
      - Thêm cột audience_reviewed (mặc định FALSE cho tài liệu cũ)
    """
    global _schema_migrated
    if _schema_migrated:
        return
    try:
        db.execute(
            text(
                """
                ALTER TABLE chatbot_documents
                ADD COLUMN IF NOT EXISTS audience JSONB NOT NULL DEFAULT '["student", "teacher", "staff", "admin"]'::jsonb;
                """
            )
        )
        db.execute(
            text(
                """
                ALTER TABLE chatbot_documents
                ADD COLUMN IF NOT EXISTS audience_reviewed BOOLEAN NOT NULL DEFAULT FALSE;
                """
            )
        )
        db.commit()
        _schema_migrated = True
    except Exception as e:
        db.rollback()
        logger.warning(f"Could not auto-migrate chatbot_documents schema: {e}")


# Step 1: Khai báo Router với ResponseWrapperRoute
router = APIRouter(tags=["Chatbot"], prefix="/chatbot", route_class=ResponseWrapperRoute)

# --- DTOs ---
class UserChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
    retrieval_mode: str = "hybrid_rerank"
    top_k: int = 4
    simulate_429: bool = False

# --- Background task for uploading to AI server ---
async def _process_upload_to_ai(
    doc_db_id: UUID,
    file_content: bytes,
    filename: str,
    content_type: str,
    doc_category: str,
    user_id: UUID,
    audience: Optional[List[str]] = None,
    audience_reviewed: bool = True,
):
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
            result = await chatbot_service.upload_document(
                pseudo_file,
                doc_category=doc_category,
                audience=audience or doc.audience or list(DEFAULT_DOCUMENT_AUDIENCE),
                audience_reviewed=audience_reviewed,
            )
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
    http_request: Request,
    current_user = Depends(get_current_user)
):
    """
    API cho Frontend gọi để chat với AI (trả về reply + danh sách sources trích dẫn + sự kiện Agent).
    """
    real_role = current_user.role.value
    auth_header = http_request.headers.get("authorization")

    try:
        response = await chatbot_service.ask_bot(
            message=request.message,
            user_role=real_role,
            history=request.history,
            retrieval_mode=request.retrieval_mode,
            top_k=request.top_k,
            user_id=str(current_user.id),
            auth_token=auth_header,
            simulate_429=request.simulate_429,
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
    http_request: Request,
    current_user = Depends(get_current_user)
):
    """
    API cho Frontend gọi để chat stream với AI (POST SSE kèm Source Citations, tool_call, ui_action).
    """
    real_role = current_user.role.value
    auth_header = http_request.headers.get("authorization")

    try:
        stream_gen = await chatbot_service.ask_bot_stream(
            message=request.message,
            user_role=real_role,
            history=request.history,
            retrieval_mode=request.retrieval_mode,
            top_k=request.top_k,
            user_id=str(current_user.id),
            auth_token=auth_header,
            simulate_429=request.simulate_429,
        )

        async def sse_wrapper():
            async for chunk in stream_gen:
                if isinstance(chunk, dict):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'text': str(chunk)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(sse_wrapper(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Error in chat stream: {e}")
        raise APIException(
            status_code=500,
            code="CHAT_STREAM_ERROR",
            message=f"An error occurred during chat stream: {str(e)}"
        )

@router.get("/stream")
async def chat_with_ai_stream_get(
    http_request: Request,
    message: str = Query(..., description="Nội dung câu hỏi"),
    retrieval_mode: str = Query("hybrid_rerank", description="Chế độ truy xuất: standard | hybrid | hybrid_rerank"),
    top_k: int = Query(4, description="Số đoạn ngữ cảnh lấy sau Rerank"),
    simulate_429: bool = Query(False, description="Giả lập lỗi 429 để kiểm thử cơ chế fallback"),
    current_user = Depends(get_current_user_optional)
):
    """
    Endpoint GET /api/v1/chatbot/stream dùng cơ chế Server-Sent Events (SSE),
    gửi từng token câu trả lời kèm metadata các tài liệu tham khảo (Source Citations) và sự kiện Agent.
    """
    real_role = current_user.role.value if current_user and hasattr(current_user, "role") else "guest"
    uid = str(current_user.id) if current_user and hasattr(current_user, "id") else None
    auth_header = http_request.headers.get("authorization")
    try:
        stream_gen = await chatbot_service.ask_bot_stream(
            message=message,
            user_role=real_role,
            history=[],
            retrieval_mode=retrieval_mode,
            top_k=top_k,
            user_id=uid,
            auth_token=auth_header,
            simulate_429=simulate_429,
        )

        async def sse_wrapper():
            async for chunk in stream_gen:
                if isinstance(chunk, dict):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'text': str(chunk)}, ensure_ascii=False)}\n\n"

        return StreamingResponse(sse_wrapper(), media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Error in GET chat stream: {e}")
        raise APIException(
            status_code=500,
            code="CHAT_STREAM_ERROR",
            message=f"An error occurred during chat stream: {str(e)}"
        )

@router.post("/evaluation/ragas-benchmark", response_model=ApiResponse[dict])
async def run_ragas_benchmark_endpoint(
    sample_size: Optional[int] = Query(None, description="Số lượng câu hỏi test (mặc định 80)"),
    current_user = Depends(get_current_admin_user)
):
    """
    Chạy đánh giá định lượng 4 chỉ số RAGAs trên bộ Ground-Truth 80 câu.
    """
    try:
        data = await chatbot_service.trigger_ragas_benchmark(sample_size=sample_size)
        return ApiResponse(data=data, message="Hoàn tất chạy đánh giá định lượng RAGAs")
    except Exception as e:
        raise APIException(status_code=500, code="RAGAS_EVAL_ERROR", message=str(e))

@router.get("/evaluation/results", response_model=ApiResponse[dict])
async def get_ragas_evaluation_results(
    current_user = Depends(get_current_user)
):
    """
    Lấy bảng số liệu đối sánh 4 metrics RAGAs và cấu hình thực nghiệm.
    """
    try:
        data = await chatbot_service.get_ragas_results()
        return ApiResponse(data=data)
    except Exception as e:
        raise APIException(status_code=500, code="RAGAS_RESULTS_ERROR", message=str(e))

@router.post("/admin/upload-doc", response_model=ApiResponse[ChatbotDocumentResponse])
async def upload_knowledge_base(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_category: str = Form("business"),
    audience: str = Form('["student","teacher","staff","admin"]'),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
):
    """
    API cho Admin upload tài liệu nội quy/giáo trình kèm phân quyền audience bắt buộc.
    Trả về ngay lập tức với status=processing, upload AI chạy nền.
    """
    _ensure_chatbot_documents_schema(db)
    normalized_aud = normalize_audience(audience, fallback=[])
    if not normalized_aud:
        raise APIException(
            status_code=400,
            code="INVALID_AUDIENCE",
            message="Vui lòng chọn ít nhất một đối tượng được phép truy xuất tài liệu (public, student, teacher, staff, admin).",
        )

    try:
        file_content = await file.read()

        new_doc = ChatbotDocument(
            doc_id=None,
            filename=file.filename,
            category=DocCategory(doc_category),
            audience=normalized_aud,
            audience_reviewed=True,
            status=DocStatus.processing,
            created_by=current_user.id
        )
        db.add(new_doc)
        db.flush()

        audit_service.log(
            db,
            action=AuditAction.CREATE,
            table_name="chatbot_documents",
            record_id=new_doc.id,
            user_id=current_user.id,
            new_values={
                "filename": file.filename,
                "category": doc_category,
                "audience": normalized_aud,
                "audience_reviewed": True,
            },
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        db.commit()
        db.refresh(new_doc)

        background_tasks.add_task(
            _process_upload_to_ai,
            doc_db_id=new_doc.id,
            file_content=file_content,
            filename=file.filename,
            content_type=file.content_type,
            doc_category=doc_category,
            user_id=current_user.id,
            audience=normalized_aud,
            audience_reviewed=True,
        )

        new_doc.uploaded_by_name = f"{current_user.first_name} {current_user.last_name}"

        return ApiResponse(data=ChatbotDocumentResponse.model_validate(new_doc, from_attributes=True))
    except APIException:
        raise
    except Exception as e:
        db.rollback()
        raise APIException(
            status_code=400,
            code="UPLOAD_FAILED",
            message=f"Failed to initiate upload: {str(e)}"
        )


@router.patch("/admin/documents/bulk-audience", response_model=ApiResponse[List[ChatbotDocumentResponse]])
async def bulk_update_document_audience(
    request: Request,
    payload: ChatbotDocumentBulkAudienceUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user),
):
    """
    Cập nhật hàng loạt quyền truy cập audience cho nhiều tài liệu cùng lúc.
    """
    _ensure_chatbot_documents_schema(db)
    normalized_aud = normalize_audience(payload.audience, fallback=[])
    if not normalized_aud:
        raise APIException(
            status_code=400,
            code="INVALID_AUDIENCE",
            message="Danh sách audience phải chứa ít nhất một giá trị hợp lệ.",
        )

    from app.models.user import User

    updated_docs: list[ChatbotDocumentResponse] = []
    for raw_id in payload.document_ids:
        doc = None
        try:
            parsed_uuid = UUID(str(raw_id))
            doc = db.query(ChatbotDocument).filter(ChatbotDocument.id == parsed_uuid).first()
        except ValueError:
            pass
        if not doc:
            doc = db.query(ChatbotDocument).filter(ChatbotDocument.doc_id == str(raw_id)).first()
        if not doc:
            continue

        old_aud = list(doc.audience) if doc.audience else list(DEFAULT_DOCUMENT_AUDIENCE)
        old_rev = bool(doc.audience_reviewed)

        if doc.doc_id and doc.status == DocStatus.completed:
            try:
                await chatbot_service.update_document_audience(
                    doc_id=doc.doc_id,
                    audience=normalized_aud,
                    audience_reviewed=payload.audience_reviewed,
                )
            except HTTPException as he:
                if he.status_code != 404:
                    raise APIException(
                        status_code=he.status_code,
                        code="AI_AUDIENCE_UPDATE_FAILED",
                        message=str(he.detail),
                    )

        doc.audience = normalized_aud
        doc.audience_reviewed = bool(payload.audience_reviewed)
        db.flush()

        audit_service.log(
            db,
            action=AuditAction.UPDATE,
            table_name="chatbot_documents",
            record_id=doc.id,
            user_id=current_user.id,
            old_values={"audience": old_aud, "audience_reviewed": old_rev},
            new_values={"audience": normalized_aud, "audience_reviewed": bool(payload.audience_reviewed)},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        user = db.query(User).filter(User.id == doc.created_by).first()
        doc.uploaded_by_name = f"{user.first_name} {user.last_name}" if user else ""
        updated_docs.append(ChatbotDocumentResponse.model_validate(doc, from_attributes=True))

    db.commit()
    return ApiResponse(
        data=updated_docs,
        message=f"Đã cập nhật phân quyền audience cho {len(updated_docs)} tài liệu.",
    )


@router.patch("/admin/documents/{doc_id}/audience", response_model=ApiResponse[ChatbotDocumentResponse])
async def update_document_audience_endpoint(
    doc_id: str,
    request: Request,
    payload: ChatbotDocumentAudienceUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user),
):
    """
    Cập nhật danh sách audience cho tài liệu đã tồn tại (không cần embedding lại file).
    Ghi nhận nhật ký kiểm toán (Audit Log).
    """
    _ensure_chatbot_documents_schema(db)
    normalized_aud = normalize_audience(payload.audience, fallback=[])
    if not normalized_aud:
        raise APIException(
            status_code=400,
            code="INVALID_AUDIENCE",
            message="Danh sách audience phải chứa ít nhất một giá trị hợp lệ (public, student, teacher, staff, admin).",
        )

    doc = None
    try:
        parsed_uuid = UUID(doc_id)
        doc = db.query(ChatbotDocument).filter(ChatbotDocument.id == parsed_uuid).first()
    except ValueError:
        pass
    if not doc:
        doc = db.query(ChatbotDocument).filter(ChatbotDocument.doc_id == doc_id).first()

    if not doc:
        raise APIException(
            status_code=404,
            code="DOC_NOT_FOUND",
            message="Không tìm thấy tài liệu trong cơ sở dữ liệu.",
        )

    old_aud = list(doc.audience) if doc.audience else list(DEFAULT_DOCUMENT_AUDIENCE)
    old_rev = bool(doc.audience_reviewed)

    try:
        if doc.doc_id and doc.status == DocStatus.completed:
            try:
                await chatbot_service.update_document_audience(
                    doc_id=doc.doc_id,
                    audience=normalized_aud,
                    audience_reviewed=payload.audience_reviewed,
                )
            except HTTPException as he:
                if he.status_code != 404:
                    raise APIException(
                        status_code=he.status_code,
                        code="AI_AUDIENCE_UPDATE_FAILED",
                        message=str(he.detail),
                    )

        doc.audience = normalized_aud
        doc.audience_reviewed = bool(payload.audience_reviewed)
        db.flush()

        audit_service.log(
            db,
            action=AuditAction.UPDATE,
            table_name="chatbot_documents",
            record_id=doc.id,
            user_id=current_user.id,
            old_values={"audience": old_aud, "audience_reviewed": old_rev},
            new_values={"audience": normalized_aud, "audience_reviewed": bool(payload.audience_reviewed)},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        db.commit()
        db.refresh(doc)

        from app.models.user import User
        user = db.query(User).filter(User.id == doc.created_by).first()
        doc.uploaded_by_name = f"{user.first_name} {user.last_name}" if user else ""

        return ApiResponse(
            data=ChatbotDocumentResponse.model_validate(doc, from_attributes=True),
            message="Đã cập nhật quyền truy cập audience cho tài liệu thành công.",
        )
    except APIException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise APIException(
            status_code=500,
            code="AUDIENCE_UPDATE_ERROR",
            message=f"Lỗi khi cập nhật quyền truy cập tài liệu: {str(e)}",
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
    _ensure_chatbot_documents_schema(db)
    from app.models.user import User

    query = db.query(ChatbotDocument, User).join(User, ChatbotDocument.created_by == User.id)

    if category:
        query = query.filter(ChatbotDocument.category == category)

    total = query.count()
    items = query.order_by(ChatbotDocument.created_at.desc()).offset(commons.skip).limit(commons.limit).all()

    results = []
    for doc, user in items:
        if not doc.audience:
            doc.audience = list(DEFAULT_DOCUMENT_AUDIENCE)
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
        doc = db.query(ChatbotDocument).filter(ChatbotDocument.id == doc_id).first()

    if not doc:
        raise APIException(
            status_code=404,
            code="DOC_NOT_FOUND",
            message="Document not found in database"
        )

    try:
        if doc.doc_id and doc.status == DocStatus.completed:
            try:
                await chatbot_service.delete_document(doc.doc_id)
            except HTTPException as he:
                if he.status_code == 404:
                    logger.warning(f"Document {doc.doc_id} not found on AI server (404), proceeding with database deletion.")
                else:
                    raise he

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
        audience=doc.audience or list(DEFAULT_DOCUMENT_AUDIENCE),
        audience_reviewed=bool(doc.audience_reviewed),
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
    _ensure_chatbot_documents_schema(db)
    doc = db.query(ChatbotDocument).filter(ChatbotDocument.doc_id == doc_id).first()
    if not doc:
        raise APIException(
            status_code=404,
            code="DOC_NOT_FOUND",
            message="Document not found in database"
        )

    try:
        try:
            await chatbot_service.delete_document(doc_id)
        except HTTPException as he:
            if he.status_code == 404:
                logger.warning(f"Document {doc_id} not found on AI server for update (404), proceeding with new upload.")
            else:
                raise he

        result = await chatbot_service.upload_document(
            file,
            doc_category=doc.category.value,
            audience=doc.audience or list(DEFAULT_DOCUMENT_AUDIENCE),
            audience_reviewed=bool(doc.audience_reviewed),
        )
        new_doc_id_from_chatbot = result.get("doc_id")

        if not new_doc_id_from_chatbot:
            raise Exception("AI Server did not return a new doc_id")

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


# ============================================================
# SCRUM-94: INTERNAL AGENT READ TOOLS FOR STUDENT
# ============================================================

def _resolve_agent_student_user(
    request: Request,
    db: Session,
    current_user_opt = None,
):
    """
    Xác thực yêu cầu gọi công cụ Agent:
    1. Nếu gọi nội bộ từ `tungtung-chatbot` kèm `x-api-key` hợp lệ và `x-agent-user-id`,
       lấy thông tin User theo `x-agent-user-id` (không tin tham số từ LLM).
    2. Hoặc xác thực qua JWT Bearer token (`current_user_opt`).
    3. Bắt buộc user phải mang vai trò `student`.
    """
    from app.core import config as app_config
    from app.models.user import User, UserRole

    internal_key = request.headers.get("x-api-key")
    expected_key = app_config.settings.CHATBOT_API_KEY
    agent_uid_header = request.headers.get("x-agent-user-id")

    user_obj = None
    if internal_key and expected_key and internal_key == expected_key and agent_uid_header:
        try:
            parsed_uid = UUID(str(agent_uid_header).strip())
            user_obj = (
                db.query(User)
                .filter(User.id == parsed_uid, User.deleted_at.is_(None))
                .first()
            )
        except ValueError:
            user_obj = None

    if user_obj is None and current_user_opt is not None:
        user_obj = current_user_opt

    if user_obj is None:
        raise APIException(
            status_code=401,
            code="AGENT_TOOL_UNAUTHORIZED",
            message="Không xác định được danh tính học viên cho công cụ Agent.",
        )

    role_val = user_obj.role.value if hasattr(user_obj.role, "value") else str(user_obj.role)
    if role_val != UserRole.STUDENT.value:
        raise APIException(
            status_code=403,
            code="AGENT_TOOL_FORBIDDEN_ROLE",
            message="Công cụ Agent chỉ được phép truy xuất dữ liệu của học viên (student).",
        )

    return user_obj


def _get_student_enrolled_class_ids(db: Session, student_id: UUID) -> List[UUID]:
    from app.models.academic import ClassEnrollment, EnrollmentStatus, Class

    rows = (
        db.query(ClassEnrollment.class_id)
        .join(Class, Class.id == ClassEnrollment.class_id)
        .filter(
            ClassEnrollment.student_id == student_id,
            ClassEnrollment.deleted_at.is_(None),
            Class.deleted_at.is_(None),
            ClassEnrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.COMPLETED]),
        )
        .all()
    )
    return [r.class_id for r in rows]


@router.get("/agent-tools/my-classes", response_model=ApiResponse[dict])
async def agent_tool_get_my_classes(
    request: Request,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_optional),
):
    """
    Công cụ `get_my_classes`: Lấy danh sách các lớp học mà học viên đang ghi danh.
    """
    from sqlalchemy.orm import joinedload
    from app.models.academic import Class, ClassEnrollment

    student = _resolve_agent_student_user(request, db, current_user)
    enrollments = (
        db.query(ClassEnrollment)
        .options(
            joinedload(ClassEnrollment.enrollment_class).joinedload(Class.course),
            joinedload(ClassEnrollment.enrollment_class).joinedload(Class.teacher),
            joinedload(ClassEnrollment.enrollment_class).joinedload(Class.room),
        )
        .filter(
            ClassEnrollment.student_id == student.id,
            ClassEnrollment.deleted_at.is_(None),
        )
        .all()
    )

    classes_list = []
    for enr in enrollments:
        cls = enr.enrollment_class
        if not cls or cls.deleted_at is not None:
            continue
        classes_list.append(
            {
                "class_id": str(cls.id),
                "class_name": cls.name,
                "course_name": cls.course.name if cls.course else None,
                "teacher_name": f"{cls.teacher.first_name} {cls.teacher.last_name}".strip() if cls.teacher else None,
                "room_name": cls.room.name if cls.room else None,
                "start_date": cls.start_date.isoformat() if cls.start_date else None,
                "end_date": cls.end_date.isoformat() if cls.end_date else None,
                "class_status": cls.status.value if hasattr(cls.status, "value") else str(cls.status),
                "enrollment_status": enr.status.value if hasattr(enr.status, "value") else str(enr.status),
            }
        )

    return ApiResponse(
        data={
            "student_id": str(student.id),
            "total_classes": len(classes_list),
            "classes": classes_list,
        }
    )


@router.get("/agent-tools/schedule", response_model=ApiResponse[dict])
async def agent_tool_get_schedule(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_optional),
):
    """
    Công cụ `get_schedule`: Lấy lịch học cá nhân của học viên theo các lớp đã ghi danh.
    """
    from datetime import date, datetime, timedelta
    from sqlalchemy.orm import joinedload
    from app.models.session_attendance import ClassSession

    student = _resolve_agent_student_user(request, db, current_user)
    enrolled_class_ids = _get_student_enrolled_class_ids(db, student.id)

    try:
        start_d = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else date.today()
    except ValueError:
        start_d = date.today()

    try:
        end_d = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else (start_d + timedelta(days=7))
    except ValueError:
        end_d = start_d + timedelta(days=7)

    if not enrolled_class_ids:
        return ApiResponse(
            data={
                "date_from": start_d.isoformat(),
                "date_to": end_d.isoformat(),
                "total_sessions": 0,
                "sessions": [],
            }
        )

    sessions = (
        db.query(ClassSession)
        .options(
            joinedload(ClassSession.session_class),
            joinedload(ClassSession.room),
            joinedload(ClassSession.teacher),
        )
        .filter(
            ClassSession.class_id.in_(enrolled_class_ids),
            ClassSession.deleted_at.is_(None),
            ClassSession.session_date >= start_d,
            ClassSession.session_date <= end_d,
        )
        .order_by(ClassSession.session_date.asc(), ClassSession.start_time.asc())
        .limit(30)
        .all()
    )

    session_items = []
    for s in sessions:
        session_items.append(
            {
                "session_id": str(s.id),
                "class_id": str(s.class_id),
                "class_name": s.session_class.name if s.session_class else "",
                "date": s.session_date.isoformat() if s.session_date else None,
                "start_time": s.start_time.strftime("%H:%M") if s.start_time else None,
                "end_time": s.end_time.strftime("%H:%M") if s.end_time else None,
                "room_name": s.room.name if s.room else None,
                "teacher_name": f"{s.teacher.first_name} {s.teacher.last_name}".strip() if s.teacher else None,
                "topic": s.topic,
                "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            }
        )

    return ApiResponse(
        data={
            "date_from": start_d.isoformat(),
            "date_to": end_d.isoformat(),
            "total_sessions": len(session_items),
            "sessions": session_items,
        }
    )


@router.get("/agent-tools/current-homework", response_model=ApiResponse[dict])
async def agent_tool_get_current_homework(
    request: Request,
    class_id: Optional[str] = Query(None, description="UUID lớp học (tùy chọn)"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_optional),
):
    """
    Công cụ `get_current_homework`: Lấy bài tập / bài kiểm tra hiện tại của học viên
    (kèm trạng thái đã nộp / chưa nộp và bài tập ghi trong buổi học gần nhất).
    """
    from app.models.test import Test, TestStatus, TestAttempt
    from app.models.session_attendance import ClassSession

    student = _resolve_agent_student_user(request, db, current_user)
    enrolled_class_ids = _get_student_enrolled_class_ids(db, student.id)

    target_class_ids = list(enrolled_class_ids)
    if class_id:
        try:
            req_cid = UUID(str(class_id).strip())
        except ValueError:
            raise APIException(status_code=400, code="INVALID_CLASS_ID", message="Mã lớp học không hợp lệ.")
        if req_cid not in enrolled_class_ids:
            raise APIException(
                status_code=403,
                code="CLASS_ACCESS_DENIED",
                message="Bạn không thuộc lớp học này nên không thể truy vấn bài tập.",
            )
        target_class_ids = [req_cid]

    homework_items = []
    if target_class_ids:
        tests = (
            db.query(Test)
            .filter(
                Test.deleted_at.is_(None),
                Test.status == TestStatus.PUBLISHED,
                Test.class_id.in_(target_class_ids),
            )
            .order_by(Test.end_time.asc().nullslast(), Test.created_at.desc())
            .limit(15)
            .all()
        )
        for t in tests:
            attempts = (
                db.query(TestAttempt)
                .filter(
                    TestAttempt.test_id == t.id,
                    TestAttempt.student_id == student.id,
                    TestAttempt.deleted_at.is_(None),
                )
                .order_by(TestAttempt.attempt_number.desc())
                .all()
            )
            latest_status = (
                attempts[0].status.value
                if attempts and hasattr(attempts[0].status, "value")
                else ("not_started" if not attempts else str(attempts[0].status))
            )
            homework_items.append(
                {
                    "type": "lms_test_or_homework",
                    "id": str(t.id),
                    "class_id": str(t.class_id) if t.class_id else None,
                    "title": t.title,
                    "test_type": t.test_type.value if hasattr(t.test_type, "value") else str(t.test_type or "homework"),
                    "due_date": t.end_time.isoformat() if t.end_time else None,
                    "attempts_used": len(attempts),
                    "max_attempts": t.max_attempts or 1,
                    "submission_status": latest_status,
                }
            )

        # Bổ sung bài tập về nhà đính kèm trong các buổi học (ClassSession.homework)
        sessions_with_hw = (
            db.query(ClassSession)
            .filter(
                ClassSession.class_id.in_(target_class_ids),
                ClassSession.deleted_at.is_(None),
                ClassSession.homework.isnot(None),
            )
            .order_by(ClassSession.session_date.desc())
            .limit(5)
            .all()
        )
        for sess in sessions_with_hw:
            if sess.homework:
                homework_items.append(
                    {
                        "type": "session_homework",
                        "session_id": str(sess.id),
                        "class_id": str(sess.class_id),
                        "session_date": sess.session_date.isoformat() if sess.session_date else None,
                        "topic": sess.topic,
                        "homework": sess.homework,
                    }
                )

    return ApiResponse(
        data={
            "total_homework": len(homework_items),
            "homework_items": homework_items,
        }
    )


@router.get("/agent-tools/unread-notifications", response_model=ApiResponse[dict])
async def agent_tool_get_unread_notifications(
    request: Request,
    limit: int = Query(5, ge=1, le=5, description="Tối đa 5 thông báo chưa đọc"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_optional),
):
    """
    Công cụ `get_unread_notifications`: Lấy tối đa 5 thông báo chưa đọc gần nhất của học viên.
    """
    from app.repositories.notification import notification_repo

    student = _resolve_agent_student_user(request, db, current_user)
    capped_limit = min(max(limit, 1), 5)
    unread_list = notification_repo.get_by_user(
        db,
        user_id=student.id,
        skip=0,
        limit=capped_limit,
        unread_only=True,
    )
    total_unread = notification_repo.count_unread(db, user_id=student.id)

    items = [
        {
            "id": str(n.id),
            "title": n.title,
            "content": n.content,
            "type": n.notification_type.value if hasattr(n.notification_type, "value") else str(n.notification_type),
            "priority": n.priority.value if hasattr(n.priority, "value") else str(n.priority),
            "action_url": n.action_url,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in unread_list
    ]

    return ApiResponse(
        data={
            "unread_count": total_unread,
            "notifications": items,
        }
    )


class AgentTargetBandUpdate(BaseModel):
    target_band: float
    target_cefr: Optional[str] = None


@router.put("/agent-tools/target-band", response_model=ApiResponse[dict])
async def agent_tool_set_target_band(
    request: Request,
    payload: AgentTargetBandUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_optional),
):
    """
    Công cụ `set_target_band`: Học viên đặt hoặc cập nhật band mục tiêu IELTS (0.0 – 9.0, bước 0.5).
    Ghi nhận nhật ký kiểm toán (`audit_logs`) với `old_values` và `new_values`.
    """
    from sqlalchemy.orm.attributes import flag_modified

    student = _resolve_agent_student_user(request, db, current_user)
    band_val = float(payload.target_band)
    if band_val < 0.0 or band_val > 9.0 or (round(band_val * 2) != band_val * 2):
        raise APIException(
            status_code=400,
            code="INVALID_TARGET_BAND",
            message="Điểm mục tiêu IELTS phải nằm trong khoảng 0.0 – 9.0 với bước nhảy 0.5.",
        )

    old_prefs = dict(student.preferences or {})
    old_target = {
        "target_band": old_prefs.get("target_band"),
        "target_cefr": old_prefs.get("target_cefr"),
    }

    new_prefs = dict(student.preferences or {})
    new_prefs["target_band"] = band_val
    if payload.target_cefr is not None:
        new_prefs["target_cefr"] = payload.target_cefr

    student.preferences = new_prefs
    flag_modified(student, "preferences")

    audit_service.log(
        db=db,
        action=AuditAction.UPDATE,
        table_name="users",
        record_id=student.id,
        user_id=student.id,
        old_values=old_target,
        new_values={
            "target_band": new_prefs.get("target_band"),
            "target_cefr": new_prefs.get("target_cefr"),
            "source": "student_agent_tool",
        },
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    db.commit()
    db.refresh(student)

    return ApiResponse(
        data={
            "student_id": str(student.id),
            "old_target_band": old_target.get("target_band"),
            "new_target_band": band_val,
            "target_cefr": new_prefs.get("target_cefr"),
            "audit_logged": True,
        },
        message=f"Đã cập nhật điểm mục tiêu IELTS thành {band_val}.",
    )


@router.get("/agent-tools/class-posts", response_model=ApiResponse[dict])
async def agent_tool_summarize_class_posts(
    request: Request,
    class_id: Optional[str] = Query(None, description="UUID lớp học (tùy chọn)"),
    limit: int = Query(5, ge=1, le=10, description="Số bài đăng gần đây cần lấy"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_optional),
):
    """
    Công cụ `summarize_class_posts`: Lấy các bài đăng bảng tin lớp học gần đây của học viên.
    Kiểm tra nghiêm ngặt học viên phải ghi danh trong lớp đó mới được phép đọc bài đăng.
    """
    from sqlalchemy.orm import joinedload
    from app.models.class_post import ClassPost

    student = _resolve_agent_student_user(request, db, current_user)
    enrolled_class_ids = _get_student_enrolled_class_ids(db, student.id)

    target_class_ids = list(enrolled_class_ids)
    if class_id:
        try:
            req_cid = UUID(str(class_id).strip())
        except ValueError:
            raise APIException(status_code=400, code="INVALID_CLASS_ID", message="Mã lớp học không hợp lệ.")
        if req_cid not in enrolled_class_ids:
            raise APIException(
                status_code=403,
                code="CLASS_ACCESS_DENIED",
                message="Bạn không ghi danh trong lớp học này nên không được xem bài đăng.",
            )
        target_class_ids = [req_cid]

    if not target_class_ids:
        return ApiResponse(data={"total_posts": 0, "posts": []})

    capped_limit = min(max(limit, 1), 10)
    posts = (
        db.query(ClassPost)
        .options(joinedload(ClassPost.author), joinedload(ClassPost.class_rel))
        .filter(
            ClassPost.class_id.in_(target_class_ids),
            ClassPost.deleted_at.is_(None),
        )
        .order_by(ClassPost.is_pinned.desc(), ClassPost.created_at.desc())
        .limit(capped_limit)
        .all()
    )

    post_items = [
        {
            "post_id": str(p.id),
            "class_id": str(p.class_id),
            "class_name": p.class_rel.name if p.class_rel else None,
            "title": p.title,
            "content": (p.content or "")[:600],
            "post_type": p.post_type.value if hasattr(p.post_type, "value") else str(p.post_type),
            "is_pinned": bool(p.is_pinned),
            "author_name": f"{p.author.first_name} {p.author.last_name}".strip() if p.author else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in posts
    ]

    return ApiResponse(
        data={
            "total_posts": len(post_items),
            "posts": post_items,
        }
    )

