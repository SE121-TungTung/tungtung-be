# tests/conftest.py
import pytest
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy.orm import Session
from uuid import uuid4

@pytest.fixture
def mock_db_session():
    """Giả lập DB Session"""
    session = MagicMock(spec=Session)
    # Mock chaining query (db.query().filter()...)
    session.query.return_value.filter.return_value = session.query.return_value
    session.query.return_value.options.return_value = session.query.return_value
    session.query.return_value.join.return_value = session.query.return_value
    session.query.return_value.order_by.return_value = session.query.return_value
    return session

@pytest.fixture
def mock_upload_service(mocker):
    """Giả lập hàm upload file của Cloudinary"""
    # Lưu ý: Cần patch đúng đường dẫn nơi hàm được import sử dụng
    return mocker.patch(
        "app.services.test.test.upload_and_save_metadata",
        side_effect=AsyncMock(return_value=MagicMock(file_path="http://mock-url.com/file.mp3"))
    )

@pytest.fixture
def sample_user_id():
    return uuid4()