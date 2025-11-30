# app/api/v1/endpoints/test.py

from fastapi import APIRouter, Depends, status, Path
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies import get_current_user, get_current_admin_user # Giả định có dependency này
from app.services.test import test_service # Giả định Service đã được khởi tạo
from app.schemas.assessment import (
    TestAttemptStart, 
    TestResponseCreate,
    TestQuestionCreate)
from uuid import UUID
from typing import Dict, Any, List
from app.models.assessment import Test, QuestionBank
from app.routers.generator import create_crud_router

base_test_router = create_crud_router(
    model=Test,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user,
    tag_prefix="Tests (Admin CRUD)",
    prefix=""
)

base_question_router = create_crud_router(
    model=QuestionBank,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user,
    tag_prefix="QuestionBank (Admin CRUD)",
    prefix=""
)

router = APIRouter(prefix="/tests", tags=["Assessment & Testing"])

@router.post("/{test_id}/questions", status_code=status.HTTP_200_OK)
async def link_questions_to_test(
    link_data: List[TestQuestionCreate],
    test_id: UUID = Path(..., description="ID của đề thi cần thêm câu hỏi"),
    db: Session = Depends(get_db),
    # Chỉ Admin/Teacher mới có quyền chỉnh sửa đề thi
    current_user = Depends(get_current_admin_user) 
) -> Dict[str, Any]:
    """
    UC: Liên kết danh sách câu hỏi vào một đề thi và tính toán lại tổng điểm.
    """
    result = await test_service.add_questions_to_test(db, test_id, link_data)
    return result

@router.post("/question-bank", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any], tags=["QuestionBank (Admin CRUD)"])
async def create_new_question(
    question_in: TestQuestionCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """UC: Tạo một câu hỏi mới trong Kho câu hỏi."""
    new_question = await test_service.create_question(db, question_in, current_user.id)
    return {"message": "Question created successfully", "question_id": new_question.id}

@router.post("/create-with-questions", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_test_and_link_questions(
    data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_admin_user)
) -> Dict[str, Any]:
    """UC: Tạo một bài thi mới và liên kết các câu hỏi ngay lập tức."""
    new_test = await test_service.create_test_with_questions(db, data, current_user.id)
    return {"message": "Test created and questions linked successfully", "test_id": new_test.id}

@router.post("/{test_id}/start", status_code=status.HTTP_201_CREATED)
async def start_test_attempt(
    test_id: UUID = Path(..., description="ID của bài thi"),
    db: Session = Depends(get_db),
    student: UUID = Depends(get_current_user)
) -> Dict[str, UUID]:
    """UC: Bắt đầu một lượt làm bài thi mới."""
    student_id = student.id 
    attempt_data = TestAttemptStart(test_id=test_id, student_id=student_id)
    attempt = await test_service.start_attempt(db, attempt_data)
    return {"attempt_id": attempt.id}

@router.post("/attempts/{attempt_id}/response", status_code=status.HTTP_200_OK)
async def save_test_response(
    response_data: TestResponseCreate,
    attempt_id: UUID = Path(..., description="ID của lần làm bài"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """UC: Lưu câu trả lời cho một câu hỏi."""
    await test_service.save_response(db, attempt_id, response_data, current_user.id)
    return {"message": "Response saved successfully"}

@router.post("/attempts/{attempt_id}/submit", status_code=status.HTTP_200_OK)
async def submit_test_attempt(
    attempt_id: UUID = Path(..., description="ID của lần làm bài cần nộp"),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """UC: Nộp bài thi, ghi lại thời gian, và chạy chấm điểm tự động."""
    attempt = await test_service.submit_and_grade(db, attempt_id, current_user.id)
    return {
        "message": "Test submitted and auto-graded.",
        "attempt_id": attempt.id,
        "total_score": attempt.total_score,
        "status": attempt.status
    }

@router.post("/attempts/{attempt_id}/review", tags=["Grading & Review"], status_code=status.HTTP_200_OK)
async def teacher_review_attempt(
    review_data: List[Dict[str, Any]],
    attempt_id: UUID = Path(..., description="ID của lần làm bài cần chấm điểm"),
    db: Session = Depends(get_db),
    # Chỉ cho phép giáo viên/admin chấm điểm
    grader_user = Depends(get_current_admin_user) 
):
    """
    UC: Giáo viên chấm điểm thủ công (Essay, Speaking) và cập nhật điểm cuối cùng.
    Input: [{question_id: UUID, teacher_score: Decimal, teacher_feedback: str}]
    """
    # GỌI HÀM SERVICE MỚI
    final_attempt = await test_service.review_and_finalize_score(db, attempt_id, review_data, grader_user.id)
    return {
        "message": "Review complete. Score finalized.",
        "attempt_id": final_attempt.id,
        "final_score": final_attempt.total_score,
        "status": final_attempt.status
    }