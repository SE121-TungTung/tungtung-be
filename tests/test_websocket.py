import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock, call
from datetime import datetime, timedelta
from uuid import uuid4
from collections import deque
from app.services.websocket import ConnectionManager, manager
from fastapi import WebSocket, WebSocketDisconnect

# Fixtures cơ bản
@pytest.fixture
def manager_instance():
    # Sử dụng một instance mới cho mỗi test
    new_manager = ConnectionManager()
    # Mock task để tránh lỗi khi cleanup
    new_manager._heartbeat_task = MagicMock()
    return new_manager

@pytest.fixture
def mock_websocket():
    # Mock WebSocket object
    mock_ws = MagicMock(spec=WebSocket)
    mock_ws.accept = AsyncMock()
    mock_ws.send_json = AsyncMock()
    mock_ws.receive_json = AsyncMock()
    return mock_ws

@pytest.fixture
def user_ids():
    return uuid4(), uuid4()

# ==============================================================================
# TEST SUITE: ConnectionManager Core Logic
# ==============================================================================

@pytest.mark.asyncio
async def test_connect_and_disconnect_single_device(manager_instance, mock_websocket, user_ids):
    user_id, _ = user_ids
    
    # 1. Connect
    conn_id = await manager_instance.connect(mock_websocket, user_id)
    
    assert user_id in manager_instance.active_connections
    assert conn_id in manager_instance.connection_metadata
    mock_websocket.accept.assert_called_once()
    
    # 2. Disconnect
    await manager_instance.disconnect(conn_id, user_id)
    
    assert user_id not in manager_instance.active_connections
    assert conn_id not in manager_instance.connection_metadata

@pytest.mark.asyncio
async def test_connect_multiple_devices(manager_instance, mock_websocket, user_ids):
    user_id, _ = user_ids
    
    # Connect Device 1
    conn_id_1 = await manager_instance.connect(mock_websocket, user_id)
    
    # Connect Device 2 (sử dụng mock khác để mô phỏng 2 thiết bị vật lý)
    mock_ws_2 = MagicMock(spec=WebSocket)
    mock_ws_2.accept = AsyncMock()
    conn_id_2 = await manager_instance.connect(mock_ws_2, user_id)
    
    assert len(manager_instance.active_connections[user_id]) == 2
    
    # Disconnect Device 1
    await manager_instance.disconnect(conn_id_1, user_id)
    assert len(manager_instance.active_connections[user_id]) == 1
    
    # Disconnect Device 2
    await manager_instance.disconnect(conn_id_2, user_id)
    assert user_id not in manager_instance.active_connections

@pytest.mark.asyncio
async def test_send_personal_message_online(manager_instance, mock_websocket, user_ids):
    user_id, _ = user_ids
    await manager_instance.connect(mock_websocket, user_id)
    
    # Cần reset mock sau khi connect để loại bỏ cuộc gọi send_json cho queued messages (nếu có)
    mock_websocket.send_json.reset_mock()
    
    message = {"data": "test_online"}
    
    result = await manager_instance.send_personal_message(message, user_id)
    
    mock_websocket.send_json.assert_called_once_with(message)
    assert result['sent'] == 1
    assert result['queued'] is False
    assert manager_instance.is_user_online(user_id) is True

@pytest.mark.asyncio
async def test_send_personal_message_offline_queuing(manager_instance, user_ids):
    user_id, _ = user_ids
    message = {"data": "test_offline"}
    
    # User offline
    result = await manager_instance.send_personal_message(message, user_id)
    
    assert result['sent'] == 0
    assert result['queued'] is True
    assert len(manager_instance.message_queues[user_id]) == 1
    assert manager_instance.message_queues[user_id][0] == message

@pytest.mark.asyncio
async def test_send_queued_messages_on_reconnect():
    manager = ConnectionManager()

    user_id = uuid4()

    # Create mock websocket
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()

    msg1 = {"id": 1, "text": "hello"}
    msg2 = {"id": 2, "text": "world"}

    # Add to queue as offline
    manager.message_queues[user_id].append(msg1)
    manager.message_queues[user_id].append(msg2)

    # Connect
    conn_id = await manager.connect(ws, user_id)

    # Assertions
    ws.accept.assert_called_once()
    assert ws.send_json.call_count == 2
    ws.send_json.assert_has_calls([call(msg1), call(msg2)], any_order=False)
    assert len(manager.message_queues[user_id]) == 0


@pytest.mark.asyncio
@patch('app.services.websocket.datetime')
async def test_check_stale_connections(mock_datetime, manager_instance, user_ids):
    """
    FIX: Sử dụng MagicMock cho _remove_connection thay vì AsyncMock
    """
    user_id_stale, user_id_active = user_ids
    conn_id_stale = "stale_1"
    conn_id_active = "active_1"

    # Giả lập thời gian hiện tại
    now = datetime(2025, 1, 1, 10, 0, 0)
    mock_datetime.utcnow.return_value = now

    # 1. Tạo kết nối STALE (ping từ 100s trước)
    manager_instance.connection_metadata[conn_id_stale] = {
        'user_id': user_id_stale,
        'connected_at': now - timedelta(seconds=120),
        'last_ping': now - timedelta(seconds=100) # > 90s, sẽ bị xóa
    }
    
    # 2. Tạo kết nối ACTIVE (ping gần đây)
    manager_instance.connection_metadata[conn_id_active] = {
        'user_id': user_id_active,
        'connected_at': now - timedelta(seconds=30),
        'last_ping': now - timedelta(seconds=10) # < 90s, sẽ được giữ lại
    }
    
    # 3. Mock _remove_connection
    with patch.object(manager_instance, '_remove_connection', new=AsyncMock()) as mock_remove:
        # 4. Chạy kiểm tra
        await manager_instance._check_stale_connections()
        
        # 5. Kiểm tra: Chỉ kết nối STALE bị xóa
        mock_remove.assert_called_once_with(conn_id_stale, user_id_stale)
    
    # 6. Kết nối ACTIVE vẫn còn
    assert conn_id_active in manager_instance.connection_metadata

@pytest.mark.asyncio
async def test_handle_ping_updates_timestamp(manager_instance, mock_websocket, user_ids):
    user_id, _ = user_ids
    
    # Connect
    conn_id = await manager_instance.connect(mock_websocket, user_id)
    initial_timestamp = manager_instance.connection_metadata[conn_id]['last_ping']
    
    # Mock thời gian trôi qua
    await asyncio.sleep(0.01)

    # Handle ping
    await manager_instance.handle_ping(conn_id)
    
    new_timestamp = manager_instance.connection_metadata[conn_id]['last_ping']
    assert new_timestamp > initial_timestamp