from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta

from app.models.assessment import Test, TestAttempt, TestResponse, TestQuestion, QuestionBank
from app.models.assessment import AttemptStatus
from decimal import Decimal
from app.schemas.assessment import TestAttemptStart, TestResponseCreate, TestQuestionLink
from typing import Tuple
# Giả định Repositories đã được DI

class TestService:
    def __init__(self, test_repo, attempt_repo, response_repo, user_repo, question_repo):
        self.test_repo = test_repo
        self.attempt_repo = attempt_repo
        self.response_repo = response_repo
        self.user_repo = user_repo
        self.question_repo = question_repo

    async def add_questions_to_test(self, db: Session, test_id: UUID, data: TestQuestionLink):
        """Liên kết danh sách câu hỏi vào một đề thi (Test) và tính lại tổng điểm."""
        
        # 1. Kiểm tra Test có tồn tại không
        test = self.test_repo.get(db, test_id)
        if not test:
            raise HTTPException(status_code=404, detail="Test not found.")

        total_points = 0
        
        # 2. Xử lý từng câu hỏi trong danh sách
        for question_id in data.question_ids:
            # Kiểm tra QuestionBank có tồn tại không
            question = self.question_repo.get(db, question_id)
            if not question:
                raise HTTPException(status_code=404, detail=f"Question ID {question_id} not found in Question Bank.")

            # 3. Kiểm tra liên kết đã tồn tại chưa (để tránh trùng lặp)
            existing_link = db.query(TestQuestion).filter(
                TestQuestion.test_id == test_id,
                TestQuestion.question_id == question_id
            ).first()

            if not existing_link:
                # 4. Tạo bản ghi liên kết (TestQuestion)
                link_data = {
                    "test_id": test_id,
                    "question_id": question_id,
                    # có thể thêm 'order' hoặc 'weight' nếu cần
                }
                # Giả định self.test_question_repo tồn tại (hoặc dùng repo cơ bản)
                self.test_question_repo.create(db, obj_in=link_data)
            
            # 5. Cộng tổng điểm
            total_points += question.points 

        # 6. Cập nhật tổng điểm của Test
        test.total_points = total_points
        self.test_repo.update(db, db_obj=test, obj_in={"total_points": total_points})

        db.commit()
        return {"message": f"Successfully linked {len(data.question_ids)} questions. Total points updated to {total_points}."}
    # =========================================================================
    # 1. START ATTEMPT (Bắt đầu làm bài)
    # =========================================================================
    async def start_attempt(self, db: Session, data: TestAttemptStart) -> TestAttempt:
        
        test = self.test_repo.get(db, data.test_id)
        if not test:
            raise HTTPException(status_code=404, detail="Test not found")
        
        # Kiểm tra Max Attempts (Ràng buộc cứng)
        current_attempts = db.query(TestAttempt).filter(
            TestAttempt.test_id == data.test_id,
            TestAttempt.student_id == data.student_id
        ).count()
        
        if current_attempts >= test.max_attempts:
            raise HTTPException(status_code=403, detail=f"Exceeded maximum attempts ({test.max_attempts}).")

        # Xác định số lần làm bài mới
        new_attempt_number = current_attempts + 1

        # Tạo bản ghi TestAttempt
        attempt_data = {
            "test_id": data.test_id,
            "student_id": data.student_id,
            "attempt_number": new_attempt_number,
            "status": AttemptStatus.IN_PROGRESS.value,
            # ip_address, user_agent có thể được thêm ở đây nếu lấy từ request header
        }
        
        new_attempt = self.attempt_repo.create(db, obj_in=attempt_data)
        db.commit()
        return new_attempt

    # =========================================================================
    # 2. SAVE RESPONSE (Lưu câu trả lời)
    # =========================================================================
    async def save_response(
        self, db: Session, attempt_id: UUID, data: TestResponseCreate, user_id: UUID
    ) -> TestResponse:

        attempt = self.attempt_repo.get(db, attempt_id)
        if not attempt or attempt.status != AttemptStatus.IN_PROGRESS:
            raise HTTPException(status_code=400, detail="Attempt not found or already submitted.")
            
        if attempt.student_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this attempt.")

        # Kiểm tra xem câu trả lời cho câu hỏi này đã tồn tại chưa
        existing_response = db.query(TestResponse).filter(
            TestResponse.attempt_id == attempt_id,
            TestResponse.question_id == data.question_id
        ).first()

        response_data = data.model_dump(exclude_unset=True)
        
        if existing_response:
            # Update phản hồi hiện có
            updated_response = self.response_repo.update(db, db_obj=existing_response, obj_in=response_data)
        else:
            # Tạo phản hồi mới
            response_data['attempt_id'] = attempt_id
            new_response = self.response_repo.create(db, obj_in=response_data)
            updated_response = new_response
            
        db.commit()
        return updated_response

    # =========================================================================
    # 3. SUBMIT & GRADE (Nộp bài và Chấm điểm tự động)
    # =========================================================================
    async def submit_and_grade(self, db: Session, attempt_id: UUID, user_id: UUID) -> TestAttempt:
        
        attempt = self.attempt_repo.get(db, attempt_id)
        if not attempt or attempt.status != AttemptStatus.IN_PROGRESS:
            raise HTTPException(status_code=400, detail="Attempt already submitted or invalid.")
            
        if attempt.student_id != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this attempt.")
        
        # 1. Ghi lại thời gian nộp bài và thời gian làm bài
        submitted_time = datetime.utcnow()
        time_taken = (submitted_time - attempt.started_at).total_seconds()
        
        attempt.submitted_at = submitted_time
        attempt.time_taken_seconds = int(time_taken)
        
        # 2. Chấm điểm Tự động (Cho các câu hỏi Multiple Choice/Đúng Sai)
        total_score = self._run_auto_grading(db, attempt)
        
        # 3. Tính toán và Cập nhật Attempt
        test = self.test_repo.get(db, attempt.test_id)
        
        attempt.total_score = total_score
        attempt.percentage_score = (total_score / test.total_points) * 100 if test.total_points else 0
        attempt.passed = attempt.percentage_score >= test.passing_score
        attempt.status = AttemptStatus.GRADED.value if not self._needs_manual_review(attempt) else AttemptStatus.SUBMITTED.value
        
        self.attempt_repo.update(db, db_obj=attempt, obj_in=attempt.model_dump())
        db.commit()
        return attempt

    # =========================================================================
    # HELPER FUNCTIONS
    # =========================================================================
    
    def _run_auto_grading(self, db: Session, attempt: TestAttempt) -> Decimal:
        """Thực hiện chấm điểm tự động cho các câu hỏi MC/Short Answer."""
        from decimal import Decimal

        responses: List[TestResponse] = attempt.responses # Giả định relationship đã hoạt động
        total_score = Decimal(0)
        
        for response in responses:
            question = self.question_repo.get(db, response.question_id)
            if not question: continue
            
            # Chỉ chấm điểm tự động cho các loại câu hỏi đơn giản (Short Answer/MC)
            if question.question_type.value in ['multiple_choice', 'short_answer']:
                is_correct, points_earned = self._check_answer(question, response)
                
                # Cập nhật phản hồi
                response.is_correct = is_correct
                response.points_earned = points_earned
                
                total_score += points_earned
            
            # Cột Flagged for Review sẽ được kiểm tra sau
            
        return total_score

    def _check_answer(self, question: QuestionBank, response: TestResponse) -> Tuple[bool, Decimal]:
        """Logic kiểm tra câu trả lời MC/Short Answer."""
        # Đây là logic giả lập:
        if question.question_type.value == 'multiple_choice':
            # Logic phức tạp: so sánh response_data với options[is_correct=true]
            # Giả định response_text chứa key/answer
            return response.response_text == question.correct_answer, question.points
            
        return False, Decimal(0) # Chưa thể chấm điểm tự động cho Short Answer
        
    def _needs_manual_review(self, attempt: TestAttempt) -> bool:
        """Kiểm tra xem bài thi có cần chấm điểm thủ công (Essay/Speaking) không."""
        # Giả định logic kiểm tra:
        # Nếu có bất kỳ câu hỏi nào là Essay/Speaking, nó cần review
        
        # Đơn giản: Check if any response is flagged or requires teacher input
        return any(resp.flagged_for_review for resp in attempt.responses) or \
               any(q.question_type.value in ['essay', 'speaking'] for q in attempt.test.questions)

    async def review_and_finalize_score(
        self, 
        db: Session, 
        attempt_id: UUID, 
        review_data: List[Dict[str, Any]], # Dữ liệu điểm/feedback từ GV
        grader_id: UUID
    ) -> TestAttempt:

        attempt = self.attempt_repo.get(db, attempt_id)
        if not attempt:
            raise HTTPException(status_code=404, detail="Attempt not found.")
        
        if attempt.status not in [AttemptStatus.SUBMITTED.value, AttemptStatus.GRADED.value]:
            raise HTTPException(status_code=400, detail="Attempt status must be submitted or awaiting review.")

        # 1. Cập nhật các phản hồi cá nhân (TestResponse)
        for review_item in review_data:
            question_id = review_item.get("question_id")
            
            response = db.query(TestResponse).filter(
                TestResponse.attempt_id == attempt_id,
                TestResponse.question_id == question_id
            ).first()

            if response:
                # Tính toán lại points_earned
                new_teacher_score = review_item.get("teacher_score", Decimal(0))
                
                update_data = {
                    "teacher_score": new_teacher_score,
                    "teacher_feedback": review_item.get("teacher_feedback"),
                    "points_earned": new_teacher_score, # Cập nhật điểm kiếm được
                    # Đánh dấu là đã chấm điểm thủ công
                    "flagged_for_review": False 
                }
                self.response_repo.update(db, db_obj=response, obj_in=update_data)

        # 2. Tính lại Tổng điểm cuối cùng (Total Score)
        
        # Lấy tổng điểm mới từ tất cả responses (cả auto và manual)
        all_responses = self.response_repo.get_multi(db, filters={"attempt_id": attempt_id}).items 
        final_score = sum(r.points_earned for r in all_responses if r.points_earned is not None)
        
        test = self.test_repo.get(db, attempt.test_id)
        
        # 3. Cập nhật trạng thái Final cho Attempt
        final_score_update = {
            "total_score": final_score,
            "percentage_score": (final_score / test.total_points) * 100 if test.total_points else 0,
            "passed": final_score >= test.passing_score,
            "status": AttemptStatus.GRADED.value, # Chuyển sang trạng thái GRADED
            "graded_by": grader_id,
            "graded_at": datetime.utcnow()
        }
        
        final_attempt = self.attempt_repo.update(db, db_obj=attempt, obj_in=final_score_update)
        db.commit()
        
        return final_attempt

test_service = TestService(
    test_repo=..., 
    attempt_repo=..., 
    response_repo=..., 
    user_repo=..., 
    question_repo=...
)