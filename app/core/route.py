import json
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

class ResponseWrapperRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_handler = super().get_route_handler()

        async def custom_handler(request: Request) -> Response:
            # 1. Chạy hàm gốc trong Router
            response: Response = await original_handler(request)

            # 2. Bỏ qua nếu không phải JSON (Ví dụ: FileResponse, Streaming)
            if not isinstance(response, JSONResponse):
                return response

            # 3. Lấy dữ liệu đã được FastAPI parse thành JSON string
            try:
                body = json.loads(response.body.decode("utf-8"))
            except Exception:
                return response # Fallback an toàn

            # 4. TRÁNH BỌC 2 LẦN: Nếu dữ liệu trả về ĐÃ CÓ chữ "success" (VD: PaginationResponse)
            if isinstance(body, dict) and "success" in body:
                return response

            # 5. Đóng gói dữ liệu thuần (list, dict, DTO) thành ApiResponse chuẩn
            wrapped_data = {
                "success": True,
                "data": body,
                "message": None
            }

            # 6. Trả về Response mới
            return JSONResponse(
                content=wrapped_data,
                status_code=response.status_code,
                headers=dict(response.headers)
            )

        return custom_handler