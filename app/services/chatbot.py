import httpx
import os
import logging
from fastapi import HTTPException, UploadFile
from app.core import config

CHATBOT_SERVICE_URL = config.settings.CHATBOT_SERVICE_URL
CHATBOT_API_KEY = config.settings.CHATBOT_API_KEY

# Setup logging thay vì dùng print
logger = logging.getLogger(__name__)

class ChatbotService:
    async def ask_bot(self, message: str, user_role: str, history: list = None):
        """
        Gửi tin nhắn sang Chatbot Service
        """
        url = f"{CHATBOT_SERVICE_URL}/message"
        payload = {
            "message": message,
            "user_role": user_role,  # Role thực lấy từ DB của Main BE
            "history": history or []
        }

        async with httpx.AsyncClient() as client:
            try:
                # Gọi API với timeout 30s
                response = await client.post(url, json=payload, timeout=30.0)
                
                if response.status_code != 200:
                    logger.error(f"Chatbot Error: {response.text}")
                    return {"reply": "Xin lỗi, Chatbot đang gặp sự cố kỹ thuật."}
                
                return response.json()
            except httpx.RequestError as e:
                logger.error(f"Connection Error: {e}")
                raise HTTPException(status_code=503, detail="Không thể kết nối tới Chatbot Service")

    async def upload_document(self, file: UploadFile):
        """
        Forward file từ Admin -> Main BE -> Chatbot Service
        """
        url = f"{CHATBOT_SERVICE_URL}/upload"
        headers = {"x-api-key": CHATBOT_API_KEY}  # Header bảo mật

        try:
            # Đọc nội dung file
            file_content = await file.read()
            
            # Cấu trúc multipart/form-data
            files = {
                "file": (file.filename, file_content, file.content_type)
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, files=files, headers=headers, timeout=60.0)
                
                if response.status_code != 200:
                    raise HTTPException(status_code=response.status_code, detail=response.text)
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Upload Error: {e}")
            raise HTTPException(status_code=500, detail="Lỗi khi upload tài liệu sang AI Server")
        finally:
            # Reset con trỏ file (best practice)
            await file.seek(0)

chatbot_service = ChatbotService()