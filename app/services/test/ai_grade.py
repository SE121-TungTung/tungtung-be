from app.models.test import QuestionBank, QuestionType
from app.core.config import settings
import httpx

class AIGradeService:
    async def ai_grade(self, question: QuestionBank, answer: str, max_points: float):
        if question.question_type == QuestionType.ESSAY.value:
            return await self.ai_grade_writing(question, answer, max_points)

        if question.question_type == QuestionType.SPEAKING.value:
            # answer = path or file reference
            return await self.ai_grade_speaking(question, answer, max_points)

        raise ValueError("Unsupported AI grading type")
    
    async def ai_grade_writing(
            self, 
            question: QuestionBank, 
            task_type: int, 
            answer: str
    ):
        async with httpx.AsyncClient(timeout=60) as client:
            payload = {
                "task_type": task_type,
                "prompt": question.question_text,
                "essay": answer,
                "image_url": question.image_url
            }

            resp = await client.post(
                f"{settings.AI_BASE_URL}/grade/writing",
                json=payload
            )

            resp.raise_for_status()
            data = resp.json()

            # score_ratio = data["overallScore"] / 9
            # points = round(score_ratio * max_points, 2)

            return {
                "raw": data
            }
        
    async def ai_grade_speaking(
        self,
        question: QuestionBank,
        audio_file_path: str
    ):
        async with httpx.AsyncClient(timeout=120) as client:
            with open(audio_file_path, "rb") as f:
                files = {
                    "audio": f
                }
                data = {
                    "prompt": question.question_text
                }

                resp = await client.post(
                    f"{settings.AI_BASE_URL}/grade/speaking",
                    data=data,
                    files=files
                )

            resp.raise_for_status()
            result = resp.json()

            # score_ratio = result["overallScore"] / 9
            # points = round(score_ratio * max_points, 2)

            return {
                "raw": result
            }

