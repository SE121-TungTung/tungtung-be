from typing import Tuple
import string
import secrets
from datetime import date, timedelta
from fastapi import Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole, UserStatus

def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Inactive user"
        )
    return current_user

def get_current_admin_user(
    current_user: User = Depends(get_current_active_user)
) -> User:
    if current_user.role not in [UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

def get_current_teacher_or_admin(
    current_user: User = Depends(get_current_active_user)
) -> User:
    allowed_roles = [UserRole.TEACHER, UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN]
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

def _get_current_week_range() -> Tuple[date, date]:
    today = date.today()
    # today.weekday() trả về 0 cho Thứ Hai, 6 cho Chủ Nhật
    days_to_monday = today.weekday() 
    
    start_of_week = today - timedelta(days=days_to_monday)
    # Giả sử tuần kết thúc vào Chủ Nhật
    end_of_week = start_of_week + timedelta(days=6) 
    
    return start_of_week, end_of_week

def generate_strong_password(length=12):
    """Tạo mật khẩu tạm thời ngẫu nhiên và mạnh."""
    
    # 1. Định nghĩa các bộ ký tự
    letters = string.ascii_letters
    digits = string.digits
    special_chars = '!@#$%^&*'
    
    # 2. Đảm bảo mật khẩu chứa ít nhất 1 ký tự từ mỗi loại
    password = [
        secrets.choice(string.ascii_uppercase), # Chữ hoa
        secrets.choice(string.ascii_lowercase), # Chữ thường
        secrets.choice(digits),                 # Số
        secrets.choice(special_chars)           # Ký tự đặc biệt
    ]
    
    # 3. Điền vào phần còn lại của mật khẩu
    all_chars = letters + digits + special_chars
    remaining_length = length - len(password)
    password.extend(secrets.choice(all_chars) for _ in range(remaining_length))
    
    # 4. Trộn lẫn các ký tự và trả về
    secrets.SystemRandom().shuffle(password)
    return "".join(password)

# Common query parameters
class CommonQueryParams:
    def __init__(
        self,
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(100, ge=1, le=100, description="Number of records to return"),
    ):
        self.skip = skip
        self.limit = limit
