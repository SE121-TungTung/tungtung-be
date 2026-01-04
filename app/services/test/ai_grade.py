# app/services/test/ai_grade.py
# UPDATE EXISTING FILE

from app.models.test import QuestionBank, QuestionType
from app.core.config import settings
import httpx
import asyncio

class AIGradeService:
    """
    Service for AI grading of Writing and Speaking
    """
    
    # Existing method - keep as is
    async def ai_grade(self, question: QuestionBank, answer: str, max_points: float):
        if question.question_type == QuestionType.ESSAY.value:
            return await self.ai_grade_writing(question, answer, max_points)

        if question.question_type == QuestionType.SPEAKING.value:
            return await self.ai_grade_speaking(question, answer, max_points)

        raise ValueError("Unsupported AI grading type")
    
    # Existing method - keep as is
    async def ai_grade_writing(
            self, 
            question: QuestionBank, 
            task_type: int, 
            answer: str
    ):
        """Grade writing task (Task 1 or Task 2)"""
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

            return {
                "raw": data
            }
    
    # ============================================================
    # UPDATE THIS METHOD - Add timeout & error handling
    # ============================================================
    
    async def ai_grade_speaking(
        self,
        question: QuestionBank,
        audio_url: str  # Changed: now receives URL instead of file path
    ):
        """
        Grade speaking question from audio URL
        
        Updated for pre-upload approach:
        - Receives Cloudinary URL instead of local file path
        - AI service downloads audio from URL
        - Better error handling with timeout
        - Returns structured response with rubric scores
        
        Args:
            question: QuestionBank object with question details
            audio_url: Cloudinary URL to audio file
            
        Returns:
            Dict with structure:
            {
                "raw": {
                    "overallScore": float (0-9 band score),
                    "rubricScores": {
                        "fluency_coherence": float,
                        "lexical_resource": float,
                        "grammatical_range": float,
                        "pronunciation": float
                    },
                    "detailedFeedback": str,
                    "transcript": str (speech-to-text)
                }
            }
        """
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:

                # 1️⃣ Download audio
                audio_resp = await client.get(audio_url)
                audio_resp.raise_for_status()
                audio_bytes = audio_resp.content

                # 2️⃣ Build multipart payload
                files = {
                    "audio": ("speech.webm", audio_bytes, "audio/webm")
                }

                data = {
                    "prompt": question.question_text,
                    "question_part": question.question_type.value
                }

                # 3️⃣ Call AI service
                resp = await client.post(
                    f"{settings.AI_BASE_URL}/grade/speaking",
                    files=files,
                    data=data
                )

                resp.raise_for_status()
                result = resp.json()

                if "overallScore" not in result:
                    raise ValueError("AI response missing overallScore")

                return {"raw": result}

        except httpx.TimeoutException:
            raise Exception("AI service timeout (speaking grading)")

        except httpx.HTTPStatusError as e:
            raise Exception(
                f"AI service error (HTTP {e.response.status_code}): {e.response.text}"
            )

        except Exception as e:
            raise Exception(f"AI grading failed: {str(e)}")
    
    # ============================================================
    # NEW METHOD: Batch grade with rate limiting
    # ============================================================
    
    async def batch_grade_speaking(
        self,
        questions_and_urls: list[tuple[QuestionBank, str]],
        max_concurrent: int = 5
    ):
        """
        Grade multiple speaking questions with concurrency limit
        
        Args:
            questions_and_urls: List of (question, audio_url) tuples
            max_concurrent: Maximum concurrent AI requests (default 5)
            
        Returns:
            List of grading results (or exceptions)
        """
        
        # Use semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def grade_with_limit(question, audio_url):
            async with semaphore:
                return await self.ai_grade_speaking(question, audio_url)
        
        # Create tasks
        tasks = [
            grade_with_limit(q, url) 
            for q, url in questions_and_urls
        ]
        
        # Execute with error handling
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return results


ai_grade_service = AIGradeService()