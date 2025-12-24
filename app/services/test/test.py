from sqlalchemy.orm import Session
from uuid import UUID
from app.schemas.test.test_create import TestCreate
from app.models.test import (
    Test,
    TestSection,
    TestSectionPart,
    QuestionBank,
    TestQuestion,
    SkillArea,
    DifficultyLevel
)
from app.schemas.test.test_read import TestResponse, TestTeacherResponse
from fastapi import HTTPException, status
from sqlalchemy.orm import joinedload
from typing import Optional

class TestService:
    async def create_test(self, db: Session, data: TestCreate, created_by: UUID):
        """
        Create a full test hierarchy:
        - Test
        - Test Sections
        - Test Section Parts
        - QuestionBank entries
        - TestQuestions linking (GLOBAL ORDER NUMBER)
        """

        # 1) Create Test
        test = Test(
            title=data.title,
            description=data.description,
            instructions=data.instructions,
            time_limit_minutes=data.time_limit_minutes,
            passing_score=data.passing_score or 60,
            max_attempts=data.max_attempts or 1,
            randomize_questions=data.randomize_questions,
            show_results_immediately=data.show_results_immediately,
            start_time=data.start_time,
            end_time=data.end_time,
            ai_grading_enabled=data.ai_grading_enabled,
            class_id=data.class_id,
            course_id=data.course_id,
            test_type=data.test_type,
            exam_type_id=data.exam_type_id,
            structure_id=data.structure_id,
            created_by=created_by
        )
        db.add(test)
        db.flush()

        # --------- FIX: GLOBAL QUESTION ORDER COUNTER ----------
        global_order = 1

        # 2) Loop Sections
        for s_index, sec in enumerate(data.sections, start=1):

            section = TestSection(
                test_id=test.id,
                structure_section_id=sec.structure_section_id,
                name=sec.name,
                skill_area=sec.skill_area,
                order_number=sec.order_number,
                instructions=sec.instructions,
                time_limit_minutes=sec.time_limit_minutes
            )
            db.add(section)
            db.flush()

            # 3) Loop Parts
            for p_index, part in enumerate(sec.parts, start=1):

                part_obj = TestSectionPart(
                    test_section_id=section.id,
                    structure_part_id=part.structure_part_id,
                    name=part.name,
                    order_number=part.order_number,
                    min_questions=part.min_questions,
                    max_questions=part.max_questions,
                    audio_url=part.audio_url,
                    image_url=part.image_url,
                    instructions=part.instructions
                )
                db.add(part_obj)
                db.flush()

                # 4) Loop Questions
                for q in part.questions:

                    # CASE 1 — Reuse question
                    if q.id:
                        question = db.query(QuestionBank).filter_by(id=q.id).first()
                        if not question:
                            raise HTTPException(
                                status_code=400,
                                detail=f"Question ID {q.id} does not exist."
                            )

                    # CASE 2 — Create new
                    else:
                        question = QuestionBank(
                            title=q.title,
                            question_text=q.question_text,
                            question_type=q.question_type,
                            skill_area=q.skill_area,
                            difficulty_level=q.difficulty_level,
                            options=q.options,
                            correct_answer=q.correct_answer,
                            rubric=q.rubric,
                            audio_url=q.audio_url,
                            image_url=q.image_url,
                            points=q.points,
                            tags=q.tags,
                            extra_metadata=q.extra_metadata,
                            created_by=created_by
                        )
                        db.add(question)
                        db.flush()

                    # ------ FIX: USE GLOBAL ORDER NUMBER --------
                    tq = TestQuestion(
                        test_id=test.id,
                        question_id=question.id,
                        part_id=part_obj.id,
                        order_number=global_order,   # <<<<<<---------------- FIXED
                        points=question.points,
                        required=True,
                    )

                    db.add(tq)
                    global_order += 1  # <<<< Increase globally

        db.commit()
        db.refresh(test)
        return test

    
    def get_test_for_student(self, db: Session, test_id: UUID):
        test = self._load_test_structure(db, test_id)
        test = self.build_test_response(test)
        return TestResponse.model_validate(test)

    def get_test_for_teacher(self, db: Session, test_id: UUID):
        test = self._load_test_structure(db, test_id)
        test = self.build_test_response(test)
        return TestTeacherResponse.model_validate(test)
    
    def list_tests(
        self, 
        db: Session, 
        skip: int = 0, 
        limit: int = 20, 
        class_id: Optional[UUID] = None, 
        status: Optional[str] = None,
        skill: Optional[str] = None 
    ):
        """
        List tests with filters and manual mapping for calculated fields.
        """
        try:
            query = db.query(Test)
            
            # Filter
            if class_id:
                query = query.filter(Test.class_id == class_id)
            if status:
                query = query.filter(Test.status == status)
            if skill:
                query = query.join(TestSection).filter(TestSection.skill_area == skill).distinct()
                
            # Eager load để lấy dữ liệu tính toán
            query = query.options(
                joinedload(Test.sections),
                joinedload(Test.questions)
            )
            
            # Query DB
            items = query.order_by(Test.created_at.desc()).offset(skip).limit(limit).all()
            
            # Map dữ liệu thủ công từ Model sang Dict (khớp với TestListResponse)
            results = []
            for test in items:
                # 1. Xác định Skill (Lấy skill của section đầu tiên hoặc Default)
                # Lưu ý: Nếu bài test tổng hợp nhiều skill, logic này lấy cái đầu tiên
                current_skill = None
                if test.sections:
                    current_skill = test.sections[0].skill_area
                else:
                    current_skill = SkillArea.READING # Default fallback nếu chưa có section
                
                # 2. Xác định Difficulty (Hiện DB Test chưa có cột này -> Default Medium)
                # Bạn có thể phát triển logic tính dựa trên độ khó trung bình câu hỏi sau
                current_difficulty = DifficultyLevel.MEDIUM 

                results.append({
                    "id": test.id,
                    "title": test.title,
                    "description": test.description,
                    "test_type": test.test_type,
                    "skill": current_skill,                 # Map vào field 'skill'
                    "difficulty": current_difficulty,       # Map vào field 'difficulty'
                    "duration_minutes": test.time_limit_minutes or 0, # Map từ time_limit_minutes
                    "total_questions": len(test.questions), # Đếm số lượng câu hỏi
                    "created_at": test.created_at
                })
                
            return results
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Internal helper methods
    def _load_test_structure(self, db: Session, test_id: UUID):
        """
        Load toàn bộ cấu trúc đề thi:
        Test → Sections → Parts → TestQuestion → QuestionBank
        """

        test = (
            db.query(Test)
            .options(
                joinedload(Test.sections)
                .joinedload(TestSection.parts)
                .joinedload(TestSectionPart.questions)
                .joinedload(TestQuestion.question)      # <== QUAN TRỌNG
            )
            .filter(Test.id == test_id, Test.deleted_at.is_(None))
            .first()
        )

        if not test:
            raise HTTPException(status_code=404, detail="Test not found")

        return test
    
    def build_test_response(self, test: Test):
        sections_data = []

        for section in test.sections:
            parts_data = []

            for part in section.parts:
                questions_data = []

                for tq in part.questions:
                    qb = tq.question

                    questions_data.append({
                        "id": qb.id,
                        "title": qb.title,
                        "question_text": qb.question_text,
                        "question_type": qb.question_type.value,
                        "difficulty_level": qb.difficulty_level.value if qb.difficulty_level else None,
                        "skill_area": qb.skill_area.value if qb.skill_area else None,
                        "options": qb.options,
                        "image_url": qb.image_url,
                        "audio_url": qb.audio_url,
                        "points": float(tq.points),   # override từ TestQuestion
                        "tags": qb.tags,
                        "extra_metadata": qb.extra_metadata,
                    })

                parts_data.append({
                    "id": part.id,
                    "name": part.name,
                    "order_number": part.order_number,
                    "min_questions": part.min_questions,
                    "max_questions": part.max_questions,
                    "image_url": part.image_url,
                    "audio_url": part.audio_url,
                    "instructions": part.instructions,
                    "questions": questions_data
                })

            sections_data.append({
                "id": section.id,
                "name": section.name,
                "order_number": section.order_number,
                "skill_area": section.skill_area.value,
                "time_limit_minutes": section.time_limit_minutes,
                "instructions": section.instructions,
                "parts": parts_data
            })

        return {
            "id": test.id,
            "title": test.title,
            "description": test.description,
            "instructions": test.instructions,
            "test_type": test.test_type.value if test.test_type else None,
            "time_limit_minutes": test.time_limit_minutes,
            "sections": sections_data
        }

test_service = TestService()