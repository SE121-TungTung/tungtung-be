from typing import Any
from fastapi import Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.schemas.base_schema import ErrorResponse, ErrorDetail
import logging

logger = logging.getLogger(__name__)

class APIException(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None):
        super().__init__(message)

        self.status_code: int = status_code
        self.code: str = code
        self.message: str = message
        self.details: Any = details

async def api_exception_handler(request: Request, exc: APIException):
    error_content = ErrorResponse(
        success=False,
        error=ErrorDetail(
            code=exc.code,
            message=exc.message,
            details=exc.details
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_content.model_dump() 
    )

async def http_exception_handler(request: Request, exc: HTTPException):
    error_content = ErrorResponse(
        error=ErrorDetail(
            code="HTTP_ERROR",
            message=str(exc.detail),
            details=None
        )
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=error_content.model_dump()
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Bắt lỗi 422 khi Pydantic/FastAPI validate data đầu vào thất bại"""
    # Lấy chi tiết lỗi đầu tiên để báo cho user
    errors = exc.errors()
    error_msg = f"Invalid input: {errors[0]['msg']} (Location: {errors[0]['loc'][-1]})" if errors else "Validation Error"

    error_content = ErrorResponse(
        success=False,
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message=error_msg,
            details=errors # Trả về toàn bộ chi tiết mảng lỗi cho Frontend dễ debug
        )
    )
    return JSONResponse(
        status_code=422,
        content=error_content.model_dump()
    )

async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unexpected error", exc_info=exc)

    error_content = ErrorResponse(
        error=ErrorDetail(
            code="INTERNAL_SERVER_ERROR",
            message="Unexpected server error",
            details=None
        )
    )

    return JSONResponse(
        status_code=500,
        content=error_content.model_dump()
    )