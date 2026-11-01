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
    def _match_quick_chitchat(self, message: str) -> str | None:
        q = unicodedata.normalize('NFC', message.strip()).lower()
        for char in [".", ",", "?", "!", "\"", "'"]:
            q = q.replace(char, "")

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
            return "Xin chào! Tôi là trợ lý ảo TungTung AI. Tôi có thể giúp gì cho bạn hôm nay? Bạn có thể hỏi tôi các thông tin về lớp học, học phí hoặc nhờ tôi giải thích kiến thức tiếng Anh nhé!"
        elif q_no_accents in thanks:
            return "Dạ, không có gì ạ! Rất vui được hỗ trợ bạn. Chúc bạn học tập tốt và gặt hái nhiều kết quả cao nhé!"
        elif q_no_accents in goodbyes:
            return "Tạm biệt bạn nhé! Chúc bạn một ngày vui vẻ và hẹn gặp lại bạn trong những buổi học tới!"
        return None

    async def ask_bot(
        self,
        message: str,
        user_role: str,
        history: list = None,
        retrieval_mode: str = "hybrid_rerank",
        top_k: int = 4,
    ):
        """
        Gửi tin nhắn sang Chatbot Service (trả về cả reply và danh sách sources trích dẫn).
        """
        quick_reply = self._match_quick_chitchat(message)
        if quick_reply:
            return {"reply": quick_reply, "sources": [], "retrieval_mode": retrieval_mode}

        url = f"{CHATBOT_SERVICE_URL}/message"
        payload = {
            "message": message,
            "user_role": user_role,
            "history": history or [],
            "retrieval_mode": retrieval_mode,
            "top_k": top_k,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=30.0)

                if response.status_code != 200:
                    logger.error(f"Chatbot Error: {response.text}")
                    return {"reply": "Xin lỗi, Chatbot đang gặp sự cố kỹ thuật.", "sources": []}

                return response.json()
            except httpx.RequestError as e:
                logger.error(f"Connection Error: {e}")
                raise HTTPException(status_code=503, detail="Không thể kết nối tới Chatbot Service")

    async def ask_bot_stream(
        self,
        message: str,
        user_role: str,
        history: list = None,
        retrieval_mode: str = "hybrid_rerank",
        top_k: int = 4,
    ):
        """
        Gửi tin nhắn dạng stream (SSE) sang Chatbot Service, bảo toàn cả token text và metadata sources trích dẫn.
        """
        quick_reply = self._match_quick_chitchat(message)
        if quick_reply:
            async def quick_generator():
                yield {"text": quick_reply, "sources": []}
            return quick_generator()

        url = f"{CHATBOT_SERVICE_URL}/message/stream"
        payload = {
            "message": message,
            "user_role": user_role,
            "history": history or [],
            "retrieval_mode": retrieval_mode,
            "top_k": top_k,
        }

        async def stream_generator():
            headers = {"x-api-key": CHATBOT_API_KEY} if CHATBOT_API_KEY else {}
            async with httpx.AsyncClient() as client:
                try:
                    async with client.stream("POST", url, json=payload, headers=headers, timeout=30.0) as response:
                        if response.status_code != 200:
                            logger.error(f"Chatbot Stream Error: Status {response.status_code}")
                            yield {"text": "Xin lỗi, Chatbot đang gặp sự cố kỹ thuật stream."}
                            return
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                try:
                                    data = json.loads(line[6:])
                                    if "sources" in data or "text" in data or "error" in data:
                                        yield data
                                except json.JSONDecodeError:
                                    continue
                except httpx.RequestError as e:
                    logger.error(f"Connection Error: {e}")
                    yield {"text": "Không thể kết nối tới Chatbot Service"}

        return stream_generator()

    async def trigger_ragas_benchmark(self, sample_size: int | None = None):
        """
        Kích hoạt đánh giá định lượng RAGAs trên Chatbot Service.
        """
        url = f"{CHATBOT_SERVICE_URL}/evaluation/ragas-benchmark"
        params = {"sample_size": sample_size} if sample_size else {}
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, params=params, timeout=180.0)
                if response.status_code != 200:
                    raise HTTPException(status_code=response.status_code, detail=response.text)
                return response.json().get("data", response.json())
            except httpx.RequestError as e:
                logger.error(f"Connection Error triggering RAGAs benchmark: {e}")
                raise HTTPException(status_code=503, detail="Không thể kết nối tới Chatbot Service")

    async def get_ragas_results(self):
        """
        Lấy bảng số liệu đánh giá định lượng RAGAs từ Chatbot Service.
        """
        url = f"{CHATBOT_SERVICE_URL}/evaluation/results"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, timeout=60.0)
                if response.status_code != 200:
                    raise HTTPException(status_code=response.status_code, detail=response.text)
                return response.json().get("data", response.json())
            except httpx.RequestError as e:
                logger.error(f"Connection Error fetching RAGAs results: {e}")
                raise HTTPException(status_code=503, detail="Không thể kết nối tới Chatbot Service")

    async def upload_document(self, file: UploadFile, doc_category: str = "business"):
        """
        Forward file từ Admin -> Main BE -> Chatbot Service
        """
        url = f"{CHATBOT_SERVICE_URL}/upload"
        headers = {"x-api-key": CHATBOT_API_KEY}
        params = {"doc_category": doc_category}

        try:
            file_content = await file.read()
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
