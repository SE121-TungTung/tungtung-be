from fastapi import APIRouter, BackgroundTasks, status, File, UploadFile, Form, Query, WebSocket, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional
import logging

from app.core.database import get_db
from app.dependencies import get_current_user, CommonQueryParams
from app.models.user import UserRole

# Step 1: Import core components
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse, PaginationResponse
from app.core.exceptions import APIException

from app.schemas.message import (
    MessageCreate, 
    ConversationResponse, 
    GroupCreateRequest, 
    AddMembersRequest, 
    GroupUpdateRequest,
    MessageResponse,
    UnreadCountResponse,
    MessageEditRequest
)

from app.services.websocket import websocket_manager
from app.services.message.sender_service import message_sender_service
from app.services.message.conversation_service import message_conversation_service
from app.services.message.interaction_service import message_interaction_service
from app.services.message.group_service import message_group_service

logger = logging.getLogger(__name__)

# Step 1: Khai báo Router với ResponseWrapperRoute
router = APIRouter(tags=["Messaging"], prefix="/messaging", route_class=ResponseWrapperRoute)

# ============================================================
# SEND & HISTORY
# ============================================================

@router.post("/send", response_model=ApiResponse[MessageResponse])
async def send_message_rest(
    message_data: MessageCreate,
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    result = await message_sender_service.handle_new_message(
        db=db,
        sender_id=current_user.id,
        message_data=message_data,
        background_tasks=background_tasks
    )
    return ApiResponse(data=result)

@router.get("/rooms/{room_id}/history", response_model=PaginationResponse[MessageResponse])
async def get_history(
    room_id: UUID,
    params: CommonQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get chat history for a room with pagination"""
    return await message_conversation_service.get_chat_history(
        db, room_id, current_user.id, params.page, params.limit
    )

# ============================================================
# CONVERSATIONS
# ============================================================

@router.get("/conversations/direct/{other_user_id}", response_model=ApiResponse[ConversationResponse])
async def get_direct_conversation(
    other_user_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get or create a direct conversation"""
    result = await message_conversation_service.get_or_create_direct_conversation(
        db, current_user.id, other_user_id
    )
    return ApiResponse(data=result)

@router.get("/conversations/all", response_model=PaginationResponse[ConversationResponse])
async def get_conversations(
    params: CommonQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get list of conversations for the current user with pagination"""
    return await message_conversation_service.get_user_conversations(
        db, current_user.id, params.skip, params.limit
    )

@router.post("/conversations/{room_id}/read", response_model=ApiResponse[bool])
async def mark_conversation_read(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Mark all messages in a conversation as read"""
    result = await message_interaction_service.mark_conversation_as_read(db, room_id, current_user.id)
    return ApiResponse(data=result)

# ============================================================
# GROUPS
# ============================================================

@router.post("/groups", status_code=status.HTTP_201_CREATED, response_model=ApiResponse[ConversationResponse])
async def create_group(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    member_ids: str = Form(...),
    avatar: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Create a new group chat"""
    try:
        parsed_member_ids = [UUID(m_id.strip()) for m_id in member_ids.split(",") if m_id.strip()]
    except ValueError:
        raise APIException(status_code=400, code="INVALID_UUID", message="Invalid UUID format in member_ids")

    data = GroupCreateRequest(
        title=title,
        description=description,
        member_ids=parsed_member_ids
    )

    result = await message_group_service.create_group_chat(
        db=db,
        group_data=data,
        avatar=avatar,
        creator_id=current_user.id
    )
    return ApiResponse(data=result)

@router.get("/groups/{room_id}", response_model=ApiResponse[ConversationResponse])
async def get_group_details(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get group details and members"""
    result = await message_group_service.get_group_details(db, room_id, current_user.id)
    return ApiResponse(data=result)

@router.post("/groups/{room_id}/members", response_model=ApiResponse[bool])
async def add_group_members(
    room_id: UUID,
    request: AddMembersRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add members to group"""
    result = await message_group_service.add_members_to_group(
        db, room_id, current_user.id, request.user_ids
    )
    return ApiResponse(data=result)

@router.delete("/groups/{room_id}/members/{user_id}", response_model=ApiResponse[bool])
async def remove_group_member(
    room_id: UUID,
    user_id: UUID,
    new_admin_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Remove a member from group"""
    result = await message_group_service.remove_member_from_group(
        db, room_id, current_user.id, user_id, new_admin_id
    )
    return ApiResponse(data=result)

@router.put("/groups/{room_id}", response_model=ApiResponse[ConversationResponse])
async def update_group(
    room_id: UUID,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update group information"""
    update_data = GroupUpdateRequest(title=title, description=description)
    result = await message_group_service.update_group_info(
        db=db,
        room_id=room_id,
        updater_id=current_user.id,
        update_data=update_data,
        avatar=avatar
    )
    return ApiResponse(data=result)

# ============================================================
# INTERACTION & SETTINGS
# ============================================================

@router.delete("/rooms/{room_id}", response_model=ApiResponse[bool])
async def delete_chat_room(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    result = await message_interaction_service.delete_chat_room(
        db=db,
        room_id=room_id,
        current_user_id=current_user.id
    )
    return ApiResponse(data=result)

@router.put("/messages/{message_id}", response_model=ApiResponse[MessageResponse])
async def edit_message(
    message_id: UUID,
    payload: MessageEditRequest, # Lấy nội dung từ Body thay vì Query
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Edit a previously sent message"""
    result = await message_interaction_service.edit_message(
        db=db, 
        message_id=message_id, 
        new_content=payload.new_content, 
        user_id=current_user.id
    )
    return ApiResponse(data=result)

@router.get("/search-messages", response_model=PaginationResponse[MessageResponse])
async def search_messages(
    query: str = Query(..., description="Search query string"),
    room_id: UUID = Query(None, description="Optional room ID to filter messages"),
    params: CommonQueryParams = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Search messages with pagination"""
    return await message_interaction_service.search_messages(
        db=db, 
        query_text=query, 
        user_id=current_user.id, 
        room_id=room_id, 
        page=params.page,
        limit=params.limit
    )

@router.get("/unread-count", response_model=ApiResponse[UnreadCountResponse])
async def get_total_unread_count(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    count = message_interaction_service.get_total_unread_count(db, current_user.id)
    return ApiResponse(data=UnreadCountResponse(unread_count=count))

@router.post("/rooms/{room_id}/mute", response_model=ApiResponse[bool])
async def mute_conversation(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    result = await message_interaction_service.toggle_mute(db, room_id, current_user.id, True)
    return ApiResponse(data=result)

@router.post("/rooms/{room_id}/unmute", response_model=ApiResponse[bool])
async def unmute_conversation(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    result = await message_interaction_service.toggle_mute(db, room_id, current_user.id, False)
    return ApiResponse(data=result)

# ============================================================
# WEBSOCKET
# ============================================================

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token")
):
    websocket_manager.websocket_connect(websocket=websocket, token=token)