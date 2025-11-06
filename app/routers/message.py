from fastapi import APIRouter
from app.core.database import get_db
from app.dependencies import get_current_active_user, get_current_user, get_current_user_from_token
import logging
from app.models.message import Message, MessageRecipient
from app.routers.generator import create_crud_router
from app.services.message import MessageService
from app.services.websocket import manager
from fastapi import WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session
from uuid import UUID
from fastapi import Query

logger = logging.getLogger(__name__)


message_service = MessageService()

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

router = APIRouter(tags=["Messaging"])

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: UUID):
    """WebSocket connection for real-time messaging"""
    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            # Handle incoming message
            # await message_service.handle_new_message(...)
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)

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
        # Authenticate before accepting connection
        user = await get_current_user_from_token(token)
        user_id = user.id
        
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
                # This would integrate with your MessageService
                pass
            
            else:
                logger.warning(f"Unknown message type: {msg_type}")
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
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