import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, call
from uuid import uuid4
from datetime import datetime
from app.services.message import MessageService
from app.models.message import MessageType, Message

# Fixtures cơ bản
@pytest.fixture
def mock_repos():
    # Mock Repositories
    return {
        "message_repo": MagicMock(),
        "recipient_repo": MagicMock(),
        "chat_room_repo": MagicMock(),
        "user_repo": MagicMock()
    }

@pytest.fixture
def mock_manager():
    # Mock ConnectionManager (manager)
    mock_man = MagicMock()
    # Mock AsyncMock cho các hàm async
    mock_man.send_personal_message = AsyncMock(return_value={'sent': 1, 'queued': False})
    return mock_man

@pytest.fixture
def message_service_instance(mock_repos, mock_manager):
    """
    FIX: Patch manager ở đúng vị trí mà MessageService sử dụng
    """
    # Patch manager trong module app.services.message (nơi MessageService import)
    with patch('app.services.message.manager', mock_manager):
        service = MessageService()
        # Gán lại mock repos
        service.message_repo = mock_repos["message_repo"]
        service.recipient_repo = mock_repos["recipient_repo"]
        service.chat_room_repo = mock_repos["chat_room_repo"]
        service.user_repo = mock_repos["user_repo"]
        yield service  # Sử dụng yield để giữ patch context

@pytest.fixture
def sender_receiver_ids():
    return uuid4(), uuid4()

# ==============================================================================
# TEST SUITE: MessageService
# ==============================================================================

### Test _get_or_create_direct_room ###

@pytest.mark.parametrize("order_swap", [False, True])
def test_get_or_create_direct_room_create(message_service_instance, mock_repos, sender_receiver_ids, order_swap):
    sender_id, receiver_id = sender_receiver_ids
    
    mock_db = MagicMock()
    # Mock db.query() để trả về None (kích hoạt tạo phòng mới)
    mock_db.query().filter().first.return_value = None 
    mock_db.flush = MagicMock() # Mock db.flush()
    
    # Giả lập: Tạo phòng mới thành công
    mock_room = MagicMock()
    mock_room.id = uuid4()
    mock_repos["chat_room_repo"].create.return_value = mock_room
    
    # Gọi hàm
    if order_swap:
        room = message_service_instance._get_or_create_direct_room(mock_db, receiver_id, sender_id)
    else:
        room = message_service_instance._get_or_create_direct_room(mock_db, sender_id, receiver_id)
        
    # Kiểm tra: Phòng đã được tạo 
    mock_repos["chat_room_repo"].create.assert_called_once()
    assert room == mock_room
    
    # Kiểm tra: participant1_id và participant2_id được sắp xếp
    _, kwargs = mock_repos["chat_room_repo"].create.call_args
    created_data = kwargs['obj_in']
    
    sorted_ids = sorted([str(sender_id), str(receiver_id)])
    assert str(created_data["participant1_id"]) == sorted_ids[0]
    assert str(created_data["participant2_id"]) == sorted_ids[1]

def test_get_or_create_direct_room_get_existing(message_service_instance, mock_repos, sender_receiver_ids):
    sender_id, receiver_id = sender_receiver_ids
    
    mock_db = MagicMock()
    # Giả lập: Tìm thấy phòng 
    mock_room = MagicMock()
    mock_db.query().filter().first.return_value = mock_room
    
    # Gọi hàm
    room = message_service_instance._get_or_create_direct_room(mock_db, sender_id, receiver_id)
        
    # Kiểm tra: Phòng đã được trả về và không gọi hàm tạo
    mock_repos["chat_room_repo"].create.assert_not_called()
    assert room == mock_room 

### Test handle_new_message ###

@pytest.mark.asyncio
async def test_handle_new_message_success(mock_repos, mock_manager, sender_receiver_ids):
    """
    FIX: Patch manager trực tiếp trong test thay vì dùng fixture
    """
    sender_id, receiver_id = sender_receiver_ids
    mock_db = MagicMock()
    
    # Mock db.commit() và db.refresh()
    mock_db.commit = MagicMock()
    mock_db.refresh = MagicMock()
    
    mock_room = MagicMock()
    mock_room.id = uuid4()

    mock_new_message = MagicMock()
    mock_new_message.id = uuid4()
    mock_new_message.created_at = datetime.now() 
    mock_repos["message_repo"].create.return_value = mock_new_message
    
    message_data = {
        "receiver_id": str(receiver_id),
        "content": "Hello B"
    }
    
    # FIX: Patch manager ở đúng nơi
    with patch('app.services.message.manager', mock_manager):
        service = MessageService()
        service.message_repo = mock_repos["message_repo"]
        service.recipient_repo = mock_repos["recipient_repo"]
        service.chat_room_repo = mock_repos["chat_room_repo"]
        service.user_repo = mock_repos["user_repo"]
        
        # Mock internal method
        with patch.object(service, '_get_or_create_direct_room', return_value=mock_room):
            # Gọi hàm
            await service.handle_new_message(mock_db, sender_id, message_data)
    
    # 1. Kiểm tra: Message đã được tạo
    mock_repos["message_repo"].create.assert_called_once()
    
    # 2. Kiểm tra: 2 bản ghi Recipient đã được tạo
    assert mock_repos["recipient_repo"].create.call_count == 2
    
    # 3. Kiểm tra: Manager đã được gọi để phân phối tin nhắn 2 lần
    assert mock_manager.send_personal_message.call_count == 2
    
    expected_payload = {
        'type': 'new_message', 
        'message_id': str(mock_new_message.id), 
        'sender_id': str(sender_id), 
        'content': 'Hello B', 
        'timestamp': str(mock_new_message.created_at)
    }
    
    mock_manager.send_personal_message.assert_any_call(expected_payload, receiver_id)
    mock_manager.send_personal_message.assert_any_call(expected_payload, sender_id)


@pytest.mark.asyncio
async def test_handle_new_message_validation_error(message_service_instance, mock_repos, sender_receiver_ids):
    sender_id, _ = sender_receiver_ids
    message_data = {"content": "Missing receiver_id"} 
    
    with pytest.raises(ValueError, match="Missing receiver_id or content"):
        await message_service_instance.handle_new_message(MagicMock(), sender_id, message_data)
        
    mock_repos["message_repo"].create.assert_not_called()


### Test get_chat_history ###

@pytest.mark.asyncio
async def test_get_chat_history_success(message_service_instance, mock_repos, sender_receiver_ids):
    # Setup IDs
    user_id, _ = sender_receiver_ids
    room_id = uuid4()
    mock_db = MagicMock()
    
    # 1. Mock Messages DB
    msg_1 = MagicMock(spec=Message, id=uuid4(), sender_id=user_id, content="Hi", created_at=datetime.now(), deleted_at=None)
    msg_2 = MagicMock(spec=Message, id=uuid4(), sender_id=uuid4(), content="Hello", created_at=datetime.now(), deleted_at=None)
    
    mock_query = MagicMock()
    mock_query.all.return_value = [msg_1, msg_2]
    mock_db.query.return_value.filter.return_value.order_by().offset().limit.return_value = mock_query

    # 2. Mock Statuses 
    mock_repos["recipient_repo"].get_statuses_for_user.return_value = {
        msg_1.id: {'read_at': datetime.now(), 'starred': False, 'deleted': False, 'archived': False},
        msg_2.id: {'read_at': None, 'starred': True, 'deleted': False, 'archived': False},
    }
    
    # 3. Gọi hàm 
    history = await message_service_instance.get_chat_history(mock_db, room_id, user_id)
    
    # 4. Kiểm tra
    assert len(history) == 2
    assert history[0]['message_id'] == str(msg_1.id)
    assert history[0]['is_read'] is True
    assert history[1]['message_id'] == str(msg_2.id)
    assert history[1]['is_read'] is False
    assert history[1]['is_starred'] is True

@pytest.mark.asyncio
async def test_get_chat_history_filters_deleted(message_service_instance, mock_repos, sender_receiver_ids):
    user_id, _ = sender_receiver_ids
    room_id = uuid4()
    mock_db = MagicMock()
    
    # 1. Mock Messages DB
    msg_1 = MagicMock(spec=Message, id=uuid4(), sender_id=user_id, content="Active", created_at=datetime.now(), deleted_at=None)
    msg_2 = MagicMock(spec=Message, id=uuid4(), sender_id=uuid4(), content="Deleted", created_at=datetime.now(), deleted_at=None)
    
    mock_query = MagicMock()
    mock_query.all.return_value = [msg_1, msg_2]
    mock_db.query.return_value.filter.return_value.order_by().offset().limit.return_value = mock_query

    # 2. Mock Statuses (msg_2 deleted)
    mock_repos["recipient_repo"].get_statuses_for_user.return_value = {
        msg_1.id: {'read_at': None, 'starred': False, 'deleted': False, 'archived': False},
        msg_2.id: {'read_at': None, 'starred': False, 'deleted': True, 'archived': False},
    }
    
    # 3. Gọi hàm 
    history = await message_service_instance.get_chat_history(mock_db, room_id, user_id)
    
    # 4. Kiểm tra: Chỉ tin nhắn Active được trả về
    assert len(history) == 1
    assert history[0]['message_id'] == str(msg_1.id)