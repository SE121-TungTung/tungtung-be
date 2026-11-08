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

VALID_AUDIENCES: tuple[str, ...] = ("public", "student", "teacher", "staff", "admin")
DEFAULT_DOCUMENT_AUDIENCE: list[str] = ["student", "teacher", "staff", "admin"]

ROLE_TO_AUDIENCES: dict[str, list[str]] = {
    "guest": ["public"],
    "guest_student": ["public"],
    "public": ["public"],
    "anonymous": ["public"],
    "general": ["public"],
    "student": ["public", "student"],
    "teacher": ["public", "teacher"],
    "ta": ["public", "teacher"],
    "office_admin": ["public", "staff"],
    "staff": ["public", "staff"],
    "center_admin": ["public", "student", "teacher", "staff", "admin"],
    "system_admin": ["public", "student", "teacher", "staff", "admin"],
    "admin": ["public", "student", "teacher", "staff", "admin"],
}


def normalize_audience(raw_audience: list[str] | str | None, fallback: list[str] | None = None) -> list[str]:
    default_list = list(fallback) if fallback is not None else list(DEFAULT_DOCUMENT_AUDIENCE)
    if raw_audience is None:
        return default_list
    items: list[str] = []
    if isinstance(raw_audience, str):
        s = raw_audience.strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    items = [str(x).strip().lower() for x in parsed]
            except Exception:
                items = [x.strip().lower() for x in s.strip("[]").split(",") if x.strip()]
        else:
            items = [x.strip().lower() for x in s.split(",") if x.strip()]
    elif isinstance(raw_audience, (list, tuple, set)):
        items = [str(x).strip().lower() for x in raw_audience if str(x).strip()]

    valid_set = {x for x in items if x in VALID_AUDIENCES}
    ordered = [aud for aud in VALID_AUDIENCES if aud in valid_set]
    return ordered if ordered else default_list


def resolve_allowed_audiences(user_role: str | None) -> list[str]:
    role_key = (user_role or "guest").strip().lower()
    return list(ROLE_TO_AUDIENCES.get(role_key, ["public"]))


class ChatbotService:
    def _internal_headers(self) -> dict[str, str]:
        return {"x-api-key": CHATBOT_API_KEY} if CHATBOT_API_KEY else {}
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
        allowed_audiences = resolve_allowed_audiences(user_role)
        payload = {
            "message": message,
            "user_role": user_role,
            "allowed_audiences": allowed_audiences,
            "history": history or [],
            "retrieval_mode": retrieval_mode,
            "top_k": top_k,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._internal_headers(),
                    timeout=30.0,
                )

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
        allowed_audiences = resolve_allowed_audiences(user_role)
        payload = {
            "message": message,
            "user_role": user_role,
            "allowed_audiences": allowed_audiences,
            "history": history or [],
            "retrieval_mode": retrieval_mode,
            "top_k": top_k,
        }

        async def stream_generator():
            headers = self._internal_headers()
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
                response = await client.post(url, params=params, headers=self._internal_headers(), timeout=180.0)
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
                response = await client.get(url, headers=self._internal_headers(), timeout=60.0)
                if response.status_code != 200:
                    raise HTTPException(status_code=response.status_code, detail=response.text)
                return response.json().get("data", response.json())
            except httpx.RequestError as e:
                logger.error(f"Connection Error fetching RAGAs results: {e}")
                raise HTTPException(status_code=503, detail="Không thể kết nối tới Chatbot Service")

    async def upload_document(
        self,
        file: UploadFile,
        doc_category: str = "business",
        audience: list[str] | None = None,
        audience_reviewed: bool = True,
    ):
        """
        Forward file từ Admin -> Main BE -> Chatbot Service kèm phân quyền audience.
        """
        url = f"{CHATBOT_SERVICE_URL}/upload"
        headers = self._internal_headers()
        normalized_aud = normalize_audience(audience)
        params = {
            "doc_category": doc_category,
            "audience": ",".join(normalized_aud),
            "audience_reviewed": str(bool(audience_reviewed)).lower(),
        }

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

    async def update_document_audience(
        self,
        doc_id: str,
        audience: list[str],
        audience_reviewed: bool = True,
    ):
        """
        Cập nhật danh sách audience cho tài liệu đã tồn tại trên AI Server (set_payload trong Qdrant).
        """
        url = f"{CHATBOT_SERVICE_URL}/documents/{doc_id}/audience"
        headers = self._internal_headers()
        normalized_aud = normalize_audience(audience, fallback=[])
        if not normalized_aud:
            raise HTTPException(status_code=400, detail="Danh sách audience không hợp lệ")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.patch(
                    url,
                    json={"audience": normalized_aud, "audience_reviewed": bool(audience_reviewed)},
                    headers=headers,
                    timeout=30.0,
                )
                if response.status_code != 200:
                    logger.error(f"Chatbot Update Audience Error: {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Lỗi khi cập nhật quyền truy cập tài liệu trên AI Server",
                    )
                return response.json()
            except httpx.RequestError as e:
                logger.error(f"Connection Error updating document audience: {e}")
                raise HTTPException(status_code=503, detail="Không thể kết nối tới Chatbot Service")

    async def delete_document(self, doc_id: str):
        """
        Gửi yêu cầu xóa document sang Chatbot Service
        """
        url = f"{CHATBOT_SERVICE_URL}/documents/{doc_id}"
        headers = self._internal_headers()
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
