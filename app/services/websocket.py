import asyncio
from typing import Dict, Set, Any, List, Optional, Tuple
from fastapi import WebSocket
from uuid import UUID
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
import logging
import secrets

from sqlalchemy.orm import Session
from app.models.message import ChatRoom, ChatRoomMember, MessageType

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # {user_id: {connection_id: WebSocket}}
        self.active_connections: Dict[UUID, Dict[str, WebSocket]] = defaultdict(dict)

        # {user_id: deque([message])}
        self.message_queues: Dict[UUID, deque] = defaultdict(lambda: deque(maxlen=100))

        # {connection_id: metadata}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}

        # {room_id: set(user_id)}
        self.room_subscriptions: Dict[UUID, Set[UUID]] = defaultdict(set)

        self.lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None

    # =====================================================
    # HEARTBEAT
    # =====================================================

    def start_heartbeat(self):
        if not self._heartbeat_task or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            logger.info("WebSocket heartbeat started")

    async def _heartbeat_loop(self):
        while True:
            try:
                await asyncio.sleep(30)
                await self._check_stale_connections()
            except Exception:
                logger.exception("Heartbeat loop error")

    async def _check_stale_connections(self):
        now = datetime.now(timezone.utc)
        stale_threshold = timedelta(seconds=90)

        # ---- PHASE 1: COLLECT (WITH LOCK) ----
        stale: List[Tuple[str, UUID]] = []

        async with self.lock:
            for conn_id, meta in self.connection_metadata.items():
                last_ping = meta.get("last_ping", meta["connected_at"])
                if now - last_ping > stale_threshold:
                    stale.append((conn_id, meta["user_id"]))

        # ---- PHASE 2: CLEANUP (NO LOCK) ----
        for conn_id, user_id in stale:
            logger.warning("Removing stale connection %s (user %s)", conn_id, user_id)
            await self.disconnect(conn_id, user_id)

    # =====================================================
    # CONNECTION LIFECYCLE
    # =====================================================

    async def connect(
        self,
        websocket: WebSocket,
        user_id: UUID,
        connection_id: Optional[str] = None
    ) -> str:
        if not connection_id:
            connection_id = f"{user_id}_{secrets.token_hex(8)}"

        now = datetime.now(timezone.utc)

        async with self.lock:
            self.active_connections[user_id][connection_id] = websocket
            self.connection_metadata[connection_id] = {
                "user_id": user_id,
                "connected_at": now,
                "last_ping": now,
            }

        self.start_heartbeat()

        logger.info(
            "WS connected | user=%s | conn=%s | devices=%d",
            user_id,
            connection_id,
            len(self.active_connections[user_id]),
        )

        await self._send_queued_messages(user_id, connection_id)
        return connection_id

    async def disconnect(self, connection_id: str, user_id: UUID):
        async with self.lock:
            self._remove_connection_no_lock(connection_id, user_id)

        logger.info(
            "WS disconnected | user=%s | conn=%s | remaining=%d",
            user_id,
            connection_id,
            len(self.active_connections.get(user_id, {})),
        )

    def _remove_connection_no_lock(self, connection_id: str, user_id: UUID):
        if user_id in self.active_connections:
            self.active_connections[user_id].pop(connection_id, None)

            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

                for room_id in list(self.room_subscriptions.keys()):
                    self.room_subscriptions[room_id].discard(user_id)
                    if not self.room_subscriptions[room_id]:
                        del self.room_subscriptions[room_id]

        self.connection_metadata.pop(connection_id, None)

    # =====================================================
    # PING
    # =====================================================

    async def handle_ping(self, connection_id: str):
        async with self.lock:
            if connection_id in self.connection_metadata:
                self.connection_metadata[connection_id]["last_ping"] = datetime.now(timezone.utc)

    # =====================================================
    # OFFLINE QUEUE
    # =====================================================

    async def _send_queued_messages(self, user_id: UUID, connection_id: str):
        async with self.lock:
            websocket = self.active_connections.get(user_id, {}).get(connection_id)
            queue = self.message_queues.get(user_id)

        if not websocket or not queue:
            return

        sent = 0
        while queue:
            msg = queue.popleft()
            try:
                await websocket.send_json(msg)
                sent += 1
            except Exception:
                queue.appendleft(msg)
                break

        if sent:
            logger.info("Sent %d queued messages to user %s", sent, user_id)

    # =====================================================
    # SEND MESSAGE
    # =====================================================

    async def send_to_user(
        self,
        user_id: UUID,
        message: Dict[str, Any],
        store_if_offline: bool = True
    ) -> Dict[str, Any]:

        # SNAPSHOT connections
        async with self.lock:
            connections = list(self.active_connections.get(user_id, {}).items())

        if not connections:
            if store_if_offline:
                self.message_queues[user_id].append(message)
                return {"sent": 0, "queued": True}
            return {"sent": 0, "queued": False}

        sent = 0
        failed: List[Tuple[str, UUID]] = []

        for conn_id, ws in connections:
            try:
                await ws.send_json(message)
                sent += 1
            except Exception:
                failed.append((conn_id, user_id))

        for conn_id, uid in failed:
            await self.disconnect(conn_id, uid)

        return {"sent": sent, "queued": False}

    async def send_personal_message(
        self,
        message: Dict[str, Any],
        user_id: UUID,
        store_if_offline: bool = True
    ):
        return await self.send_to_user(user_id, message, store_if_offline)

    # =====================================================
    # ROOM BROADCAST (DB-BASED, GIỮ NGUYÊN)
    # =====================================================

    async def broadcast_to_users(self, message: Dict[str, Any], user_ids: List[UUID]):
        results = await asyncio.gather(
            *[self.send_to_user(uid, message) for uid in user_ids],
            return_exceptions=True
        )

        return {
            "sent_users": sum(1 for r in results if isinstance(r, dict) and r.get("sent", 0) > 0),
            "queued_users": sum(1 for r in results if isinstance(r, dict) and r.get("queued")),
            "total_users": len(user_ids),
        }
    
    async def broadcast_to_room(
        self,
        room_id: UUID,
        message: dict,
        db_session: Session,
        exclude_user_id: UUID | None = None
    ):
        """
        Broadcast message to all ONLINE users in a room (Group / Class)
        - Room membership is loaded from DB (source of truth)
        - Only sends to connected users
        """

        # 1️⃣ Lấy room
        room = db_session.query(ChatRoom).filter(ChatRoom.id == room_id).first()
        if not room:
            return

        recipient_user_ids: list[UUID] = []

        # 2️⃣ Xác định danh sách user theo room type
        if room.room_type == MessageType.DIRECT:
            # Direct chat: chỉ 2 người
            if room.participant1_id:
                recipient_user_ids.append(room.participant1_id)
            if room.participant2_id:
                recipient_user_ids.append(room.participant2_id)

        elif room.room_type in [MessageType.GROUP, MessageType.CLASS]:
            members = db_session.query(ChatRoomMember.user_id).filter(
                ChatRoomMember.chat_room_id == room_id
            ).all()
            recipient_user_ids = [m.user_id for m in members]

        # 3️⃣ Broadcast cho từng user online
        for user_id in recipient_user_ids:
            if exclude_user_id and user_id == exclude_user_id:
                continue

            if user_id in self.active_connections:
                await self.send_to_user(user_id, message)

    # =====================================================
    # STATS
    # =====================================================

    async def get_stats(self):
        async with self.lock:
            total_connections = sum(len(v) for v in self.active_connections.values())
            return {
                "total_users_online": len(self.active_connections),
                "total_connections": total_connections,
                "avg_devices_per_user": (
                    total_connections / len(self.active_connections)
                    if self.active_connections else 0
                ),
            }


manager = ConnectionManager()
