import asyncio
from fastapi import APIRouter, HTTPException, status, Query # Thêm HTTPException và status
from app.core.database import get_db, SessionLocal
from app.dependencies import get_current_active_user, get_current_user, get_current_user_from_token
import logging
from app.models.message import Message, MessageRecipient
from app.schemas.message import MessageCreate, ConversationResponse, GroupCreateRequest, GroupDetailResponse, MemberResponse, AddMembersRequest, GroupUpdateRequest
from app.routers.generator import create_crud_router
from app.services.message import message_service
from app.services.websocket import manager
from fastapi import WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List
from app.models.message import ChatRoom

logger = logging.getLogger(__name__)


message_service = message_service

base_message_router = create_crud_router(
    model=Message,
    db_dependency=get_db,
    auth_dependency=get_current_active_user,
    tag_prefix="Messages (CRUD)",
    prefix=""
)

base_recepient_router = create_crud_router(
    model=MessageRecipient,
    db_dependency=get_db,
    auth_dependency=get_current_active_user,
    tag_prefix="MessageRecipients (CRUD)",
    prefix=""
)

router = APIRouter(tags=["Messaging"], prefix="/messaging")

@router.post("/send")
async def send_message_rest(
    message_data: MessageCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return await message_service.handle_new_message(
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
    return await message_service.get_chat_history(
        db, room_id, current_user.id, skip, limit
    )


@router.get("/conversations/direct/{other_user_id}")
async def get_direct_conversation(
    other_user_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get or create a direct conversation between current user and another user"""
    return await message_service.get_or_create_direct_conversation(
        db, current_user.id, other_user_id
    )

@router.get("/conversations/all", response_model=List[ConversationResponse])
async def get_conversations(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get list of conversations for the current user"""
    return await message_service.get_user_conversations(
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
    return await message_service.mark_conversation_as_read(db, room_id, current_user.id)

@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(
    group_data: GroupCreateRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new group chat"""
    return await message_service.create_group_chat(
        db, current_user.id, group_data
    )

@router.get("/groups/{room_id}")
async def get_group_details(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get group details and members"""
    members_data = await message_service.get_group_members(db, room_id, current_user.id)
    
    # Get room info
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Group not found")
    
    return GroupDetailResponse(
        id=room.id,
        title=room.title,
        description=room.description,
        avatar_url=room.avatar_url,
        room_type=room.room_type.value,
        created_at=room.created_at,
        member_count=len(members_data),
        members=[MemberResponse(
            user_id=m['user_id'],
            role=m['role'],
            joined_at=m['joined_at'],
            nickname=m.get('nickname'),
            full_name=m.get('full_name'),
            avatar_url=m.get('avatar_url'),
            email=m.get('email'),
            is_online=m.get('is_online')
        ) for m in members_data]
    )

@router.post("/groups/{room_id}/members")
async def add_group_members(
    room_id: UUID,
    request: AddMembersRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Add members to group"""
    return await message_service.add_members_to_group(
        db, room_id, current_user.id, request.user_ids
    )

@router.delete("/groups/{room_id}/members/{user_id}")
async def remove_group_member(
    room_id: UUID,
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Remove a member from group"""
    return await message_service.remove_member_from_group(
        db, room_id, current_user.id, user_id
    )

@router.put("/groups/{room_id}")
async def update_group(
    room_id: UUID,
    update_data: GroupUpdateRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update group information (admin only)"""
    # Check if user is admin
    from app.models.message import ChatRoomMember, MemberRole
    
    member = db.query(ChatRoomMember).filter(
        ChatRoomMember.chat_room_id == room_id,
        ChatRoomMember.user_id == current_user.id
    ).first()
    
    if not member or member.role != MemberRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can update group")
    
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Group not found")
    
    if update_data.title:
        room.title = update_data.title
    if update_data.description is not None:
        room.description = update_data.description
    if update_data.avatar_url is not None:
        room.avatar_url = update_data.avatar_url
    
    db.commit()
    db.refresh(room)
    
    return room

@router.post("/edit_message/{message_id}")
async def edit_message(
    message_id: UUID,
    new_content: str = Query(..., description="New content for the message"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Edit a previously sent message"""
    return await message_service.edit_message(
        db, message_id, new_content, current_user.id,
    )

@router.get("/search_messages")
async def search_messages(
    query: str = Query(..., description="Search query string"),
    room_id: UUID = Query(None, description="Optional room ID to filter messages"),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Search messages containing the query string, optionally within a specific room"""
    return await message_service.search_messages(
        db, query, current_user.id, room_id, skip, limit
    )

@router.get("/unread-count")
async def get_total_unread_count(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    count = message_service.get_total_unread_count(db, current_user.id)
    return {"unread_count": count}

@router.post("/rooms/{room_id}/mute")
async def mute_conversation(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return await message_service.toggle_mute(db, room_id, current_user.id, True)

@router.post("/rooms/{room_id}/unmute")
async def unmute_conversation(
    room_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return await message_service.toggle_mute(db, room_id, current_user.id, False)

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token for authentication")
):
    """
    WebSocket endpoint with authentication
    
    Client usage:
    ws://localhost:8000/api/v1/ws?token=<jwt_token>
    """
    connection_id = None
    user_id = None
    
    try:
        # 1. AUTHENTICATE (trước khi chấp nhận kết nối)
        user = await get_current_user_from_token(token)
        user_id = user.id
        
        # 2. CHẤP NHẬN KẾT NỐI VÀ THÊM VÀO MANAGER
        # Accept connection
        connection_id = await manager.connect(websocket, user_id)
        
        # Send welcome message
        await websocket.send_json({
            'type': 'connected',
            'message': 'WebSocket connection established',
            'user_id': str(user_id),
            'connection_id': connection_id
        })
        
        # Message loop
        while True:
            data = await websocket.receive_json()
            
            # Handle different message types
            msg_type = data.get('type')
            
            if msg_type == 'ping':
                # Heartbeat
                await manager.handle_ping(connection_id)
                await websocket.send_json({'type': 'pong'})
            
            elif msg_type == 'typing':
                # Typing indicator
                room_id = data.get('room_id')
                is_typing = data.get('is_typing', False)
                await manager.send_typing_indicator(user_id, UUID(room_id), is_typing)
            
            elif msg_type == 'message':
                # New message - delegate to MessageService
                db = SessionLocal() # Khởi tạo session thủ công
                try:
                    await message_service.handle_new_message(
                        db=db, 
                        sender_id=user_id, 
                        message_data=data
                    )
                except Exception as e:
                    logger.error(f"Error handling new message: {e}", exc_info=True)
                    await websocket.send_json({
                        'type': 'error',
                        'message': f'Failed to send message: {str(e)}'
                    })
                finally:
                    db.close()
            
            else:
                logger.warning(f"Unknown message type: {msg_type}")
    
    except HTTPException as e:
        # Xử lý LỖI XÁC THỰC: Ngay lập tức đóng kết nối
        # KHÔNG GỌI websocket.accept() nếu auth thất bại.
        # Nếu exception xảy ra trước accept(), chỉ cần return.
        # Nếu exception xảy ra sau accept(), nó sẽ được bắt ở khối Exception chung.
        if websocket.client_state.name == 'CONNECTING':
             # Tùy chọn: Gửi lỗi trước khi đóng nếu có thể
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning(f"WebSocket authentication failed for token. Status: {e.status_code}")
        # Kết thúc request
        return 
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        # Bắt các lỗi chung khác xảy ra SAU KHI kết nối đã được chấp nhận
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        # Dọn dẹp chỉ khi connection_id đã được thiết lập (tức là connection đã được chấp nhận)
        if connection_id and user_id:
            await manager.disconnect(connection_id, user_id)


@router.get("/ws/stats")
async def get_websocket_stats(
    current_user = Depends(get_current_user)
):
    """Get WebSocket connection statistics (admin only)"""
    return await manager.get_stats()

@router.get("/ws/online-users")
async def get_online_users(
    current_user = Depends(get_current_user)
):
    """Get list of online users"""
    return {
        'online_users': [str(uid) for uid in manager.get_online_users()],
        'total': len(manager.get_online_users())
    }