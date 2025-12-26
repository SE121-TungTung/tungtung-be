from sqlalchemy.orm import Session, joinedload
from uuid import UUID
from fastapi import HTTPException

from app.schemas.test.test_create import TestCreate
from app.schemas.test.test_read import TestResponse, TestTeacherResponse

from app.models.test import (
    Test,
    TestSection,
    TestSectionPart,
    QuestionGroup,
    QuestionBank,
    TestQuestion,
    TestStatus
)


class TestService:

    # ============================================================
    # CREATE TEST
    # ============================================================
    async def create_test(self, db: Session, data: TestCreate, created_by: UUID):

        test = Test(
            title=data.title,
            description=data.description,
            instructions=data.instructions,
            time_limit_minutes=data.time_limit_minutes,
            passing_score=data.passing_score or 60,
            max_attempts=data.max_attempts or 1,
            randomize_questions=data.randomize_questions or False,
            show_results_immediately=data.show_results_immediately or False,
            start_time=data.start_time,
            end_time=data.end_time,
            ai_grading_enabled=data.ai_grading_enabled or False,
            class_id=data.class_id,
            course_id=data.course_id,
            test_type=data.test_type,
            exam_type_id=data.exam_type_id,
            structure_id=data.structure_id,
            created_by=created_by,
            status=TestStatus.DRAFT
        )

        db.add(test)
        db.flush()

        global_order = 1

        # =========================
        # Sections
        # =========================
        for sec in data.sections:
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

            # =========================
            # Parts
            # =========================
            for part in sec.parts:
                part_obj = TestSectionPart(
                    test_section_id=section.id,
                    structure_part_id=part.structure_part_id,
                    name=part.name,
                    order_number=part.order_number,
                    content=part.content,
                    min_questions=part.min_questions,
                    max_questions=part.max_questions,
                    audio_url=part.audio_url,
                    image_url=part.image_url,
                    instructions=part.instructions
                )
                db.add(part_obj)
                db.flush()

                # =========================
                # Question Groups (NEW)
                # =========================
                for group_data in part.question_groups:
                    group = QuestionGroup(
                        part_id=part_obj.id,
                        name=group_data.name,
                        order_number=group_data.order_number,
                        question_type=group_data.question_type,
                        instructions=group_data.instructions,
                        image_url=group_data.image_url
                    )
                    db.add(group)
                    db.flush()

                    # =========================
                    # Questions
                    # =========================
                    for q in group_data.questions:

                        # Reuse question
                        if q.id:
                            question = db.query(QuestionBank).filter(
                                QuestionBank.id == q.id,
                                QuestionBank.deleted_at.is_(None)
                            ).first()

                            if not question:
                                raise HTTPException(400, f"Question {q.id} not found")

                            if question.question_type != q.question_type:
                                raise HTTPException(
                                    400,
                                    "Question type mismatch when reusing question"
                                )

                        # Create new question
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

                        # Link question to test
                        test_question = TestQuestion(
                            test_id=test.id,
                            group_id=group.id,
                            question_id=question.id,
                            order_number=global_order,
                            points=q.points,
                            required=True
                        )
                        db.add(test_question)
                        global_order += 1

        db.commit()
        db.refresh(test)
        return test


    # ============================================================
    # READ TEST
    # ============================================================
    def get_test_for_student(self, db: Session, test_id: UUID):
        test = self._load_test_structure(db, test_id, for_student=True)
        return TestResponse.model_validate(self.build_test_response(test))

    def get_test_for_teacher(self, db: Session, test_id: UUID):
        test = self._load_test_structure(db, test_id, for_student=False)
        return TestTeacherResponse.model_validate(self.build_test_response(test))

    # ============================================================
    # LOAD STRUCTURE
    # ============================================================
    def _load_test_structure(self, db: Session, test_id: UUID, for_student: bool):

        query = (
            db.query(Test)
            .options(
                joinedload(Test.sections)
                .joinedload(TestSection.parts)
                .joinedload(TestSectionPart.question_groups)
                .joinedload(QuestionGroup.test_questions)
                .joinedload(TestQuestion.question)
            )
            .filter(Test.id == test_id, Test.deleted_at.is_(None))
        )

        if for_student:
            query = query.filter(Test.status == TestStatus.PUBLISHED)

        test = query.first()
        if not test:
            raise HTTPException(404, "Test not found")

        return test

    # ============================================================
    # BUILD RESPONSE
    # ============================================================
    def build_test_response(self, test: Test):
        sections = []

        for section in test.sections:
            parts = []

            for part in section.parts:
                groups = []

                for group in part.question_groups:
                    questions = []

                    for tq in group.test_questions:
                        qb = tq.question
                        questions.append({
                            "id": qb.id,
                            "title": qb.title,
                            "question_text": qb.question_text,
                            "question_type": qb.question_type.value,
                            "difficulty_level": qb.difficulty_level.value if qb.difficulty_level else None,
                            "skill_area": qb.skill_area.value if qb.skill_area else None,
                            "options": qb.options,
                            "image_url": qb.image_url,
                            "audio_url": qb.audio_url,
                            "points": float(tq.points),
                            "tags": qb.tags,
                            "visible_metadata": qb.extra_metadata,
                        })

                    groups.append({
                        "id": group.id,
                        "name": group.name,
                        "order_number": group.order_number,
                        "question_type": group.question_type.value if hasattr(group.question_type, "value") else group.question_type,
                        "instructions": group.instructions,
                        "image_url": group.image_url,
                        "questions": questions
                    })

                parts.append({
                    "id": part.id,
                    "name": part.name,
                    "order_number": part.order_number,
                    "content": part.content,
                    "min_questions": part.min_questions,
                    "max_questions": part.max_questions,
                    "image_url": part.image_url,
                    "audio_url": part.audio_url,
                    "instructions": part.instructions,
                    "question_groups": groups
                })

            sections.append({
                "id": section.id,
                "name": section.name,
                "order_number": section.order_number,
                "skill_area": section.skill_area.value,
                "time_limit_minutes": section.time_limit_minutes,
                "instructions": section.instructions,
                "parts": parts
            })

        return {
            "id": test.id,
            "title": test.title,
            "description": test.description,
            "instructions": test.instructions,
            "test_type": test.test_type.value if test.test_type else None,
            "time_limit_minutes": test.time_limit_minutes,
            "sections": sections
        }


test_service = TestService()
