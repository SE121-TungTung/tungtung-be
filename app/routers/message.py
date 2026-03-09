from fastapi import APIRouter, HTTPException, status, File, UploadFile, Form, Query # Thêm HTTPException và status
from app.core.database import get_db
from app.dependencies import get_current_active_user, get_current_user
import logging
from app.models.message import Message, MessageRecipient
from app.schemas.message import MessageCreate, ConversationResponse, GroupCreateRequest, AddMembersRequest, GroupUpdateRequest
from app.routers.generator import create_crud_router
from fastapi import WebSocket, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional
from app.schemas.message import ConversationResponse

from app.services.websocket import websocket_manager
from app.services.message.sender_service import message_sender_service
from app.services.message.conversation_service import message_conversation_service
from app.services.message.interaction_service import message_interaction_service
from app.services.message.group_service import message_group_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Messaging"], prefix="/messaging")

@router.post("/send")
async def send_message_rest(
    message_data: MessageCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return await message_sender_service.handle_new_message(
        db,
        sender_id=current_user.id,
        message_data=message_data
    )

@router.get("/rooms/{room_id}/history")
async def get_history(
    room_id: UUID,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get chat history for a room"""
    return await message_conversation_service.get_chat_history(
        db, room_id, current_user.id, skip, limit
    )


@router.get("/conversations/direct/{other_user_id}")
async def get_direct_conversation(
    other_user_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get or create a direct conversation between current user and another user"""
    return await message_conversation_service.get_or_create_direct_conversation(
        db, current_user.id, other_user_id
    )

@router.get("/conversations/all", response_model=List[ConversationResponse])
async def get_conversations(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get list of conversations for the current user"""
    return await message_conversation_service.get_user_conversations(
        db, current_user.id
    )

@router.post("/conversations/{room_id}/read")
async def mark_conversation_read(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Mark all messages in a conversation as read.
    Frontend should call this when user opens a chat room.
    """
    return await message_interaction_service.mark_conversation_as_read(db, room_id, current_user.id)

@router.post("/groups", status_code=status.HTTP_201_CREATED)
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
        raise HTTPException(status_code=400, detail="Invalid UUID format in member_ids")

    data = GroupCreateRequest(
        title=title,
        description=description,
        member_ids=parsed_member_ids
    )

    return await message_group_service.create_group_chat(
        db=db,
        group_data=data,
        avatar=avatar,
        creator_id=current_user.id
    )

@router.get("/groups/{room_id}")
async def get_group_details(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get group details and members"""
    return await message_group_service.get_group_details(
        db, room_id, current_user.id
    )

@router.post("/groups/{room_id}/members")
async def add_group_members(
    room_id: UUID,
    request: AddMembersRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add members to group"""
    return await message_group_service.add_members_to_group(
        db, room_id, current_user.id, request.user_ids
    )

@router.delete("/groups/{room_id}/members/{user_id}")
async def remove_group_member(
    room_id: UUID,
    user_id: UUID,
    new_admin_id: Optional[UUID],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Remove a member from group"""
    return await message_group_service.remove_member_from_group(
        db, room_id, current_user.id, user_id, new_admin_id
    )

@router.put("/groups/{room_id}")
async def update_group(
    room_id: UUID,
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    avatar: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update group information (room admin only, support avatar upload)"""

    update_data = GroupUpdateRequest(
        title=title,
        description=description
    )

    return await message_group_service.update_group_info(
        db=db,
        room_id=room_id,
        updater_id=current_user.id,
        update_data=update_data,
        avatar=avatar
    )


@router.delete(
    "/rooms/{room_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a chat room"
)
async def delete_chat_room(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    return await message_interaction_service.delete_chat_room(
        db=db,
        room_id=room_id,
        current_user_id=current_user.id
    )

@router.post("/edit-message/{message_id}")
async def edit_message(
    message_id: UUID,
    new_content: str = Query(..., description="New content for the message"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Edit a previously sent message"""
    return await message_interaction_service.edit_message(
        db, message_id, new_content, current_user.id,
    )

@router.get("/search-messages")
async def search_messages(
    query: str = Query(..., description="Search query string"),
    room_id: UUID = Query(None, description="Optional room ID to filter messages"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Search messages containing the query string, optionally within a specific room"""
    return await message_interaction_service.search_messages(
        db, query, current_user.id, room_id, skip, limit
    )

@router.get("/unread-count")
async def get_total_unread_count(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    count = message_interaction_service.get_total_unread_count(db, current_user.id)
    return {"unread_count": count}

@router.post("/rooms/{room_id}/mute")
async def mute_conversation(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return await message_interaction_service.toggle_mute(db, room_id, current_user.id, True)

@router.post("/rooms/{room_id}/unmute")
async def unmute_conversation(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return await message_interaction_service.toggle_mute(db, room_id, current_user.id, False)

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token")
):
    websocket_manager.websocket_connect(websocket=websocket,token=token)