from typing import Generic, List, TypeVar, Optional, Any
from pydantic import BaseModel, Field

T = TypeVar("T")

class PaginationMetadata(BaseModel):
    page: int = Field(..., description="Trang hiện tại")
    limit: int = Field(..., description="Số lượng bản ghi trên mỗi trang")
    total: int = Field(..., description="Tổng số bản ghi")
    total_pages: int = Field(..., description="Tổng số trang")

class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None

    model_config = {
        "from_attributes": True
    }

class PaginationResponse(BaseModel, Generic[T]):
    success: bool = True
    data: List[T] = None
    message: Optional[str] = None
    meta: Optional[PaginationMetadata] = None

    model_config = {
        "from_attributes": True
    }

class ErrorDetail(BaseModel):
    code: str = Field(..., description="Mã lỗi hệ thống (VD: USER_NOT_FOUND)")
    message: str = Field(..., description="Thông báo lỗi thân thiện với người dùng")
    details: Optional[Any] = Field(None, description="Chi tiết lỗi (VD: validation errors)")

class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail