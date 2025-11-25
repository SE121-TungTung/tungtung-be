import asyncio
from typing import Dict, Set, Any, List, Optional
from fastapi import WebSocket, WebSocketDisconnect
from uuid import UUID
from datetime import datetime, timedelta
from collections import defaultdict, deque
import json
import logging
import secrets

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Multi-device support: {user_id: {connection_id: WebSocket}}
        self.active_connections: Dict[UUID, Dict[str, WebSocket]] = defaultdict(dict)
        
        # Message queue for offline users: {user_id: deque([message1, message2])}
        self.message_queues: Dict[UUID, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Connection metadata: {connection_id: {user_id, connected_at, last_ping}}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
        
        # Room subscriptions: {room_id: Set[user_id]} - Track who's in which room
        self.room_subscriptions: Dict[UUID, Set[UUID]] = defaultdict(set)
        
        # Lock for thread-safety
        self.lock = asyncio.Lock()
        
        # Start heartbeat task
        self._heartbeat_task = None
    
    def start_heartbeat(self):
        """Start background heartbeat checker"""
        if not self._heartbeat_task or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    async def _heartbeat_loop(self):
        """Background task to check stale connections"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30s
                await self._check_stale_connections()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _check_stale_connections(self):
        """Remove connections without ping in last 90 seconds"""
        now = datetime.utcnow()
        stale_threshold = timedelta(seconds=90)
        
        async with self.lock:
            stale_connections = []
            
            for conn_id, metadata in self.connection_metadata.items():
                last_ping = metadata.get('last_ping', metadata['connected_at'])
                if now - last_ping > stale_threshold:
                    stale_connections.append(conn_id)
            
            for conn_id in stale_connections:
                user_id = self.connection_metadata[conn_id]['user_id']
                logger.warning(f"Removing stale connection {conn_id} for user {user_id}")
                await self._remove_connection(conn_id, user_id)
    
    async def connect(
        self, 
        websocket: WebSocket, 
        user_id: UUID,
        connection_id: str = None
    ) -> str:
        """
        Accept WebSocket connection with multi-device support
        Returns: connection_id
        """
        await websocket.accept()
        
        # Generate connection_id if not provided
        if not connection_id:
            connection_id = f"{user_id}_{secrets.token_hex(8)}"
        
        async with self.lock:
            # Add connection
            self.active_connections[user_id][connection_id] = websocket
            
            # Store metadata
            self.connection_metadata[connection_id] = {
                'user_id': user_id,
                'connected_at': datetime.utcnow(),
                'last_ping': datetime.utcnow()
            }
        
        logger.info(
            f"User {user_id} connected (conn_id: {connection_id}). "
            f"Total devices: {len(self.active_connections[user_id])}"
        )
        
        # Send queued messages
        await self._send_queued_messages(user_id, connection_id)
        
        return connection_id
    
    async def _send_queued_messages(self, user_id: UUID, connection_id: str):
        """Send queued offline messages"""
        if user_id not in self.message_queues or not self.message_queues[user_id]:
            return
        
        # Get websocket reference with lock protection
        websocket = None
        async with self.lock:
            user_connections = self.active_connections.get(user_id)
            if user_connections:
                websocket = user_connections.get(connection_id)
        
        if not websocket:
            logger.warning(
                f"Cannot send queued messages: "
                f"connection {connection_id} not found for user {user_id}"
            )
            return
        
        logger.info(f"Sending {len(self.message_queues[user_id])} queued messages to {user_id}")
        
        sent_count = 0
        while self.message_queues[user_id]:
            message = self.message_queues[user_id].popleft()
            try:
                await websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send queued message to {user_id}: {e}")
                self.message_queues[user_id].appendleft(message)
                break
        
        logger.info(f"Successfully sent {sent_count} queued messages to {user_id}")
    
    async def disconnect(self, connection_id: str, user_id: UUID):
        """Remove specific connection"""
        async with self.lock:
            await self._remove_connection(connection_id, user_id)
        
        logger.info(
            f"Connection {connection_id} for user {user_id} disconnected. "
            f"Remaining devices: {len(self.active_connections.get(user_id, {}))}"
        )
    
    async def _remove_connection(self, connection_id: str, user_id: UUID):
        """Internal method to remove connection (no lock)"""
        if user_id in self.active_connections:
            if connection_id in self.active_connections[user_id]:
                del self.active_connections[user_id][connection_id]
            
            # Clean up if no more connections
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                # Remove from all room subscriptions
                for room_id in list(self.room_subscriptions.keys()):
                    self.room_subscriptions[room_id].discard(user_id)
                    if not self.room_subscriptions[room_id]:
                        del self.room_subscriptions[room_id]
        
        if connection_id in self.connection_metadata:
            del self.connection_metadata[connection_id]
    
    async def handle_ping(self, connection_id: str):
        """Update last ping time for connection"""
        if connection_id in self.connection_metadata:
            self.connection_metadata[connection_id]['last_ping'] = datetime.utcnow()
    
    async def send_to_user(
        self, 
        user_id: UUID,
        message: Dict[str, Any], 
        store_if_offline: bool = True
    ) -> Dict[str, Any]:
        """
        Send message to all user's devices
        Returns: {sent: int, queued: bool}
        """
        sent_count = 0
        
        async with self.lock:
            user_connections = self.active_connections.get(user_id, {})
        
        if not user_connections:
            # User offline
            if store_if_offline:
                self.message_queues[user_id].append(message)
                logger.info(f"User {user_id} offline. Message queued.")
                return {'sent': 0, 'queued': True}
            return {'sent': 0, 'queued': False}
        
        # Send to all devices
        disconnected = []
        for conn_id, websocket in user_connections.items():
            try:
                await websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send to {conn_id}: {e}")
                disconnected.append((conn_id, user_id))
        
        # Clean up failed connections
        for conn_id, uid in disconnected:
            await self.disconnect(conn_id, uid)
        
        return {'sent': sent_count, 'queued': False}
    
    # Alias for backward compatibility
    async def send_personal_message(
        self, 
        message: Dict[str, Any], 
        user_id: UUID,
        store_if_offline: bool = True
    ) -> Dict[str, Any]:
        """Alias for send_to_user (backward compatibility)"""
        return await self.send_to_user(user_id, message, store_if_offline)
    
    async def broadcast_to_users(
        self, 
        message: Dict[str, Any], 
        user_ids: List[UUID]
    ) -> Dict[str, Any]:
        """
        Broadcast to multiple users
        Returns: {sent_users: int, queued_users: int}
        """
        results = await asyncio.gather(
            *[self.send_to_user(uid, message) for uid in user_ids],
            return_exceptions=True
        )
        
        sent_users = sum(1 for r in results if isinstance(r, dict) and r.get('sent', 0) > 0)
        queued_users = sum(1 for r in results if isinstance(r, dict) and r.get('queued', False))
        
        return {
            'sent_users': sent_users,
            'queued_users': queued_users,
            'total_users': len(user_ids)
        }
    
    async def subscribe_to_room(self, user_id: UUID, room_id: UUID):
        """Subscribe user to room updates (for active listening)"""
        async with self.lock:
            self.room_subscriptions[room_id].add(user_id)
        logger.info(f"User {user_id} subscribed to room {room_id}")
    
    async def unsubscribe_from_room(self, user_id: UUID, room_id: UUID):
        """Unsubscribe user from room updates"""
        async with self.lock:
            self.room_subscriptions[room_id].discard(user_id)
            if not self.room_subscriptions[room_id]:
                del self.room_subscriptions[room_id]
        logger.info(f"User {user_id} unsubscribed from room {room_id}")
    
    async def broadcast_to_room(
        self, 
        room_id: UUID,
        message: Dict[str, Any], 
        exclude_user: UUID = None,
        db_session = None
    ) -> Dict[str, Any]:
        """
        Broadcast message to all members of a chat room
        
        Args:
            room_id: Room to broadcast to
            message: Message to send
            exclude_user: Optional user_id to exclude (e.g., message sender)
            db_session: Optional DB session to fetch members if needed
        
        Returns:
            {sent_users: int, queued_users: int, total_members: int}
        """
        from app.models.message import ChatRoomMember
        
        # Get room members from database
        if db_session is None:
            from app.core.database import SessionLocal
            db = SessionLocal()
            should_close = True
        else:
            db = db_session
            should_close = False
        
        try:
            # Fetch all members of the room
            members = db.query(ChatRoomMember).filter(
                ChatRoomMember.chat_room_id == room_id
            ).all()
            
            member_ids = [m.user_id for m in members if m.user_id != exclude_user]
            
            if not member_ids:
                return {
                    'sent_users': 0,
                    'queued_users': 0,
                    'total_members': 0
                }
            
            logger.info(
                f"Broadcasting to room {room_id}: "
                f"{len(member_ids)} members (excluding sender)"
            )
            
            # Broadcast to all members
            result = await self.broadcast_to_users(message, member_ids)
            result['total_members'] = len(member_ids)
            
            return result
            
        except Exception as e:
            logger.error(f"Error broadcasting to room {room_id}: {e}", exc_info=True)
            return {
                'sent_users': 0,
                'queued_users': 0,
                'total_members': 0,
                'error': str(e)
            }
        finally:
            if should_close:
                db.close()
    
    async def send_typing_indicator(
        self, 
        user_id: UUID, 
        room_id: UUID, 
        is_typing: bool
    ):
        """Send typing indicator to other room participants"""
        message = {
            'type': 'typing_indicator',
            'user_id': str(user_id),
            'room_id': str(room_id),
            'is_typing': is_typing,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Broadcast to room, excluding the typing user
        await self.broadcast_to_room(
            room_id=room_id,
            message=message,
            exclude_user=user_id
        )
    
    async def notify_member_added(
        self,
        room_id: UUID,
        added_user_ids: List[UUID],
        added_by_user_id: UUID,
        room_title: str
    ):
        """Notify room members when new members are added"""
        message = {
            'type': 'members_added',
            'room_id': str(room_id),
            'room_title': room_title,
            'added_user_ids': [str(uid) for uid in added_user_ids],
            'added_by': str(added_by_user_id),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_room(room_id, message)
    
    async def notify_member_removed(
        self,
        room_id: UUID,
        removed_user_id: UUID,
        removed_by_user_id: UUID,
        room_title: str
    ):
        """Notify room members when a member is removed"""
        message = {
            'type': 'member_removed',
            'room_id': str(room_id),
            'room_title': room_title,
            'removed_user_id': str(removed_user_id),
            'removed_by': str(removed_by_user_id),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_room(room_id, message)
        
        # Also notify the removed user specifically
        await self.send_to_user(removed_user_id, {
            **message,
            'type': 'you_were_removed'
        })
    
    async def notify_group_updated(
        self,
        room_id: UUID,
        updated_by_user_id: UUID,
        updates: Dict[str, Any]
    ):
        """Notify room members when group info is updated"""
        message = {
            'type': 'group_updated',
            'room_id': str(room_id),
            'updated_by': str(updated_by_user_id),
            'updates': updates,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_room(room_id, message)
    
    def get_online_users(self) -> List[UUID]:
        """Get list of currently online users"""
        return list(self.active_connections.keys())
    
    def is_user_online(self, user_id: UUID) -> bool:
        """Check if user has any active connections"""
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0
    
    def get_user_device_count(self, user_id: UUID) -> int:
        """Get number of active devices for user"""
        return len(self.active_connections.get(user_id, {}))
    
    def get_room_online_members(self, room_id: UUID) -> List[UUID]:
        """Get list of online members in a room"""
        if room_id not in self.room_subscriptions:
            return []
        return [uid for uid in self.room_subscriptions[room_id] if self.is_user_online(uid)]
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        async with self.lock:
            return {
                'total_users_online': len(self.active_connections),
                'total_connections': sum(len(conns) for conns in self.active_connections.values()),
                'total_rooms_active': len(self.room_subscriptions),
                'queued_messages': {
                    str(user_id): len(queue) 
                    for user_id, queue in self.message_queues.items() 
                    if len(queue) > 0
                },
                'avg_devices_per_user': (
                    sum(len(conns) for conns in self.active_connections.values()) / 
                    len(self.active_connections) if self.active_connections else 0
                )
            }

# Global instance
manager = ConnectionManager()