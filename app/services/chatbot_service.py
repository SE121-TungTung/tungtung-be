import httpx
import os
import logging
import unicodedata
import json
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
        # Fast path for greetings/chitchat (local rule-based detection to bypass LLM latency)
        # Normalize to NFC and lower case
        q = unicodedata.normalize('NFC', message.strip()).lower()
        for char in [".", ",", "?", "!", "\"", "'"]:
            q = q.replace(char, "")
        
        # Remove accents/diacritics for robust matching
        nfkd_form = unicodedata.normalize('NFKD', q)
        q_no_accents = "".join([c for c in nfkd_form if not unicodedata.combining(c)]).replace('đ', 'd').replace('Đ', 'D')
        
        greetings = {
            "xin chao", "hello", "hi", "chao", "chao ban", "chao ad", "chao chatbot",
            "hey", "alo", "e", "hello ad", "hello chatbot", "hi ad", "chao buoi sang",
            "chao buoi chieu", "chao buoi toi", "good morning", "good afternoon", "good evening"
        }
        thanks = {
            "cam on", "thank you", "thanks", "tks", "cam on ban", "cam on ad"
        }
        goodbyes = {
            "tam biet", "bye", "goodbye", "tam biet ad", "tam biet chatbot"
        }
        
        if q_no_accents in greetings:
            return {"reply": "Xin chào! Tôi là trợ lý ảo TungTung AI. Tôi có thể giúp gì cho bạn hôm nay? Bạn có thể hỏi tôi các thông tin về lớp học, học phí hoặc nhờ tôi giải thích kiến thức tiếng Anh nhé!"}
        elif q_no_accents in thanks:
            return {"reply": "Dạ, không có gì ạ! Rất vui được hỗ trợ bạn. Chúc bạn học tập tốt và gặt hái nhiều kết quả cao nhé!"}
        elif q_no_accents in goodbyes:
            return {"reply": "Tạm biệt bạn nhé! Chúc bạn một ngày vui vẻ và hẹn gặp lại bạn trong những buổi học tới!"}

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

    async def ask_bot_stream(self, message: str, user_role: str, history: list = None):
        """
        Gửi tin nhắn dạng stream sang Chatbot Service
        """
        # Fast path for greetings/chitchat (local rule-based detection to bypass LLM latency)
        # Normalize to NFC and lower case
        q = unicodedata.normalize('NFC', message.strip()).lower()
        for char in [".", ",", "?", "!", "\"", "'"]:
            q = q.replace(char, "")
        
        # Remove accents/diacritics for robust matching
        nfkd_form = unicodedata.normalize('NFKD', q)
        q_no_accents = "".join([c for c in nfkd_form if not unicodedata.combining(c)]).replace('đ', 'd').replace('Đ', 'D')
        
        greetings = {
            "xin chao", "hello", "hi", "chao", "chao ban", "chao ad", "chao chatbot",
            "hey", "alo", "e", "hello ad", "hello chatbot", "hi ad", "chao buoi sang",
            "chao buoi chieu", "chao buoi toi", "good morning", "good afternoon", "good evening"
        }
        thanks = {
            "cam on", "thank you", "thanks", "tks", "cam on ban", "cam on ad"
        }
        goodbyes = {
            "tam biet", "bye", "goodbye", "tam biet ad", "tam biet chatbot"
        }
        
        quick_reply = None
        if q_no_accents in greetings:
            quick_reply = "Xin chào! Tôi là trợ lý ảo TungTung AI. Tôi có thể giúp gì cho bạn hôm nay? Bạn có thể hỏi tôi các thông tin về lớp học, học phí hoặc nhờ tôi giải thích kiến thức tiếng Anh nhé!"
        elif q_no_accents in thanks:
            quick_reply = "Dạ, không có gì ạ! Rất vui được hỗ trợ bạn. Chúc bạn học tập tốt và gặt hái nhiều kết quả cao nhé!"
        elif q_no_accents in goodbyes:
            quick_reply = "Tạm biệt bạn nhé! Chúc bạn một ngày vui vẻ và hẹn gặp lại bạn trong những buổi học tới!"

        if quick_reply:
            async def quick_generator():
                yield quick_reply
            return quick_generator()

        url = f"{CHATBOT_SERVICE_URL}/message/stream"
        payload = {
            "message": message,
            "user_role": user_role,
            "history": history or []
        }

        async def stream_generator():
            headers = {"x-api-key": CHATBOT_API_KEY} if CHATBOT_API_KEY else {}
            async with httpx.AsyncClient() as client:
                try:
                    async with client.stream("POST", url, json=payload, headers=headers, timeout=30.0) as response:
                        if response.status_code != 200:
                            logger.error(f"Chatbot Stream Error: Status {response.status_code}")
                            yield "Xin lỗi, Chatbot đang gặp sự cố kỹ thuật stream."
                            return
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                try:
                                    data = json.loads(line[6:])
                                    if "text" in data:
                                        yield data["text"]
                                except json.JSONDecodeError:
                                    continue
                except httpx.RequestError as e:
                    logger.error(f"Connection Error: {e}")
                    yield "Không thể kết nối tới Chatbot Service"

        return stream_generator()

    async def upload_document(self, file: UploadFile, doc_category: str = "business"):
        """
        Forward file từ Admin -> Main BE -> Chatbot Service
        """
        url = f"{CHATBOT_SERVICE_URL}/upload"
        headers = {"x-api-key": CHATBOT_API_KEY}  # Header bảo mật
        params = {"doc_category": doc_category}

        try:
            # Đọc nội dung file
            file_content = await file.read()
            
            # Cấu trúc multipart/form-data
            files = {
                "file": (file.filename, file_content, file.content_type)
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, files=files, headers=headers, params=params, timeout=60.0)
                
                if response.status_code != 200:
                    raise HTTPException(status_code=response.status_code, detail=response.text)
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Upload Error: {e}")
            raise HTTPException(status_code=500, detail="Lỗi khi upload tài liệu sang AI Server")
        finally:
            # Reset con trỏ file (best practice)
            await file.seek(0)

    async def delete_document(self, doc_id: str):
        """
        Gửi yêu cầu xóa document sang Chatbot Service
        """
        url = f"{CHATBOT_SERVICE_URL}/documents/{doc_id}"
        headers = {"x-api-key": CHATBOT_API_KEY}
        async with httpx.AsyncClient() as client:
            try:
                response = await client.delete(url, headers=headers, timeout=30.0)
                if response.status_code != 200:
                    logger.error(f"Chatbot Error: {response.text}")
                    raise HTTPException(status_code=response.status_code, detail="Lỗi khi xoá tài liệu trên AI Server")
                return response.json()
            except httpx.RequestError as e:
                logger.error(f"Connection Error: {e}")
                raise HTTPException(status_code=503, detail="Không thể kết nối tới Chatbot Service")

chatbot_service = ChatbotService()