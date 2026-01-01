from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from uuid import UUID
from fastapi import HTTPException
from typing import Optional, List
from datetime import datetime

from app.schemas.test.test_create import TestCreate
from app.schemas.test.test_read import TestResponse, TestTeacherResponse
from app.models.test import ContentPassage

from fastapi import UploadFile
from app.services.cloudinary import upload_and_save_metadata

from app.models.test import (
    Test,
    TestSection,
    TestSectionPart,
    QuestionGroup,
    QuestionBank,
    TestQuestion,
    TestStatus,
    TestAttempt,
    AttemptStatus,
    DifficultyLevel,
    SkillArea
)


class TestService:

    # ============================================================
    # CREATE TEST
    # ============================================================
    from app.services.cloudinary import upload_and_save_metadata
from app.models.file_upload import UploadType, AccessLevel

class TestService:
    # ...

    async def create_test(
        self,
        db: Session,
        data: TestCreate,
        created_by: UUID,
        files: Optional[List[UploadFile]] = None
    ):
        try:
            uploaded_map = {}

            if files:
                for file in files:
                    file_meta = await upload_and_save_metadata(
                        db=db,
                        file=file,
                        uploader_id=created_by,
                        upload_type=UploadType.AUDIO,
                        access_level=AccessLevel.PUBLIC
                    )

                    if not file_meta or not file_meta.file_path:
                        raise HTTPException(
                            status_code=500,
                            detail=f"Upload failed for file {file.filename}"
                        )

                    uploaded_map[file.filename] = file_meta.file_path

            def resolve_url(url: Optional[str]) -> Optional[str]:
                if not url:
                    return None
                prefix = "file:"
                if url.startswith(prefix):
                    filename = url[len(prefix):]
                    if filename not in uploaded_map:
                        raise HTTPException(
                            status_code=400,
                            detail=f"File placeholder {filename} not found in uploads"
                        )
                    return uploaded_map[filename]
                return url

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

                for part in sec.parts:
    # ================= CREATE PASSAGE IF INLINE =================
                    passage_id = part.passage_id

                    if not passage_id and part.passage:
                        new_passage = ContentPassage(
                            title=part.passage.title,
                            content_type=part.passage.content_type,
                            text_content=part.passage.text_content,
                            audio_url=resolve_url(part.passage.audio_url),
                            image_url=resolve_url(part.passage.image_url),
                            topic=part.passage.topic,
                            difficulty_level=part.passage.difficulty_level,
                            word_count=part.passage.word_count,
                            duration_seconds=part.passage.duration_seconds,
                            created_by=created_by
                        )
                        db.add(new_passage)
                        db.flush()

                        passage_id = new_passage.id

                    part_obj = TestSectionPart(
                        test_section_id=section.id,
                        structure_part_id=part.structure_part_id,
                        name=part.name,
                        order_number=part.order_number,
                        passage_id=passage_id,
                        min_questions=part.min_questions,
                        max_questions=part.max_questions,
                        audio_url=resolve_url(part.audio_url),
                        image_url=resolve_url(part.image_url),
                        instructions=part.instructions
                    )
                    db.add(part_obj)
                    db.flush()


                    for group_data in part.question_groups:
                        group = QuestionGroup(
                            part_id=part_obj.id,
                            name=group_data.name,
                            order_number=group_data.order_number,
                            question_type=group_data.question_type,
                            instructions=group_data.instructions,
                            image_url=resolve_url(group_data.image_url)
                        )
                        db.add(group)
                        db.flush()

                        group_order = 1

                        for q in group_data.questions:
                            if q.id:
                                question = db.query(QuestionBank).filter(
                                    QuestionBank.id == q.id,
                                    QuestionBank.deleted_at.is_(None)
                                ).first()
                                if not question:
                                    raise HTTPException(
                                        status_code=400,
                                        detail=f"Question {q.id} not found"
                                    )
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
                                    audio_url=resolve_url(q.audio_url),
                                    image_url=resolve_url(q.image_url),
                                    points=q.points,
                                    tags=q.tags,
                                    extra_metadata=q.extra_metadata,
                                    created_by=created_by
                                )
                                db.add(question)
                                db.flush()

                            db.add(TestQuestion(
                                test_id=test.id,
                                group_id=group.id,
                                question_id=question.id,
                                order_number=global_order,
                                group_order_number=group_order,
                                points=q.points,
                                required=True
                            ))

                            global_order += 1
                            group_order += 1

            db.commit()
            db.refresh(test)
            return test

        except Exception:
            db.rollback()
            raise

    def update_test(
        self,
        db: Session,
        test_id: UUID,
        payload,
        user_id: UUID
    ):
        test = (
            db.query(Test)
            .filter(
                Test.id == test_id,
                Test.deleted_at.is_(None)
            )
            .first()
        )

        if not test:
            raise HTTPException(404, "Test not found")

        # Không cho sửa test đã có attempt
        has_attempt = db.query(TestAttempt).filter(
            TestAttempt.test_id == test.id
        ).first()

        if has_attempt and payload.status == TestStatus.DRAFT:
            raise HTTPException(
                400,
                "Cannot unpublish test that already has attempts"
            )

        for field, value in payload.dict(exclude_unset=True).items():
            setattr(test, field, value)

        test.updated_by = user_id

        db.commit()
        db.refresh(test)

        return test
    
    def delete_test(self, db: Session, test_id: UUID, user_id: UUID):
        test = db.query(Test).filter(
            Test.id == test_id,
            Test.deleted_at.is_(None)
        ).first()

        if not test:
            raise HTTPException(404, "Test not found")

        test.deleted_at = datetime.utcnow()
        test.updated_by = user_id

        db.commit()

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
    # LIST TESTS
    # ============================================================
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
                    "created_at": test.created_at,
                    "status": test.status
                })
                
            return {
                "total": query.count(),
                "skip": skip,
                "limit": limit,
                "tests": results
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


    def list_tests_for_student(
        self,
        db: Session,
        student_id: UUID,
        class_id: Optional[UUID] = None,
        skill: Optional[SkillArea] = None,
        skip: int = 0,
        limit: int = 20
    ):
        """
        List PUBLISHED tests available for students with optimized eager loading
        """
        from datetime import datetime, timezone
        from sqlalchemy import func, case
        
        now = datetime.now(timezone.utc)
        
        # ============================================================
        # Base query với eager loading
        # ============================================================
        query = (
            db.query(Test)
            .options(
                joinedload(Test.sections),
                joinedload(Test.questions)
            )
            .filter(
                Test.deleted_at.is_(None),
                Test.status == TestStatus.PUBLISHED
            )
        )
        
        # ============================================================
        # Time-based filters
        # ============================================================
        query = query.filter(
            (Test.start_time.is_(None)) | (Test.start_time <= now),
            (Test.end_time.is_(None)) | (Test.end_time >= now)
        )
        
        # ============================================================
        # Optional filters
        # ============================================================
        if class_id:
            query = query.filter(Test.class_id == class_id)
        
        if skill:
            # Join với TestSection để filter theo skill_area
            query = query.join(TestSection).filter(
                TestSection.skill_area == skill
            ).distinct()
        
        # ============================================================
        # Count total trước khi pagination
        # ============================================================
        total = query.count()
        
        # ============================================================
        # Pagination và ordering
        # ============================================================
        query = query.order_by(
            Test.start_time.desc().nullslast(),
            Test.created_at.desc()
        )
        
        tests = query.offset(skip).limit(limit).all()
        
        # ============================================================
        # Batch load attempts cho tất cả tests trong 1 query
        # ============================================================
        test_ids = [test.id for test in tests]
        
        # Subquery để đếm attempts per test
        attempts_subq = (
            db.query(
                TestAttempt.test_id,
                func.count(TestAttempt.id).label('count'),
                func.max(TestAttempt.attempt_number).label('max_attempt')
            )
            .filter(
                TestAttempt.test_id.in_(test_ids),
                TestAttempt.student_id == student_id
            )
            .group_by(TestAttempt.test_id)
            .subquery()
        )
        
        # Query attempts data trong 1 lần
        attempts_data = (
            db.query(
                attempts_subq.c.test_id,
                attempts_subq.c.count,
                attempts_subq.c.max_attempt
            )
            .all()
        )
        
        # Map attempts data theo test_id
        attempts_map = {
            str(row.test_id): {
                'count': row.count,
                'max_attempt': row.max_attempt
            }
            for row in attempts_data
        }
        
        # ============================================================
        # Batch load latest attempts
        # ============================================================
        latest_attempts_subq = (
            db.query(
                TestAttempt.test_id,
                TestAttempt.id,
                TestAttempt.status,
                TestAttempt.total_score,
                func.row_number().over(
                    partition_by=TestAttempt.test_id,
                    order_by=TestAttempt.attempt_number.desc()
                ).label('rn')
            )
            .filter(
                TestAttempt.test_id.in_(test_ids),
                TestAttempt.student_id == student_id
            )
            .subquery()
        )
        
        latest_attempts = (
            db.query(
                latest_attempts_subq.c.test_id,
                latest_attempts_subq.c.status,
                latest_attempts_subq.c.total_score
            )
            .filter(latest_attempts_subq.c.rn == 1)
            .all()
        )
        
        # Map latest attempts
        latest_map = {
            str(row.test_id): {
                'status': row.status,
                'score': row.total_score
            }
            for row in latest_attempts
        }
        
        # ============================================================
        # Build response
        # ============================================================
        results = []
        for test in tests:
            test_id_str = str(test.id)

            # ============================
            # Skill (giống list_tests)
            # ============================
            if test.sections:
                current_skill = test.sections[0].skill_area
            else:
                current_skill = SkillArea.READING

            # ============================
            # Difficulty (default)
            # ============================
            current_difficulty = DifficultyLevel.MEDIUM

            # Get attempts info từ map
            attempt_info = attempts_map.get(test_id_str, {'count': 0, 'max_attempt': 0})
            attempts_count = attempt_info['count']

            # Get latest attempt info
            latest = latest_map.get(test_id_str, {'status': None, 'score': None})

            # Calculate can_attempt
            can_attempt = attempts_count < (test.max_attempts or 1)

            # Count questions (đã eager load)
            total_questions = len(test.questions)

            results.append({
                "id": test.id,
                "title": test.title,
                "description": test.description,
                "test_type": test.test_type.value if test.test_type else None,

                # ✅ BỔ SUNG ĐÚNG YÊU CẦU
                "skill": current_skill,
                "difficulty": current_difficulty,
                "duration_minutes": test.time_limit_minutes or 0,
                "created_at": test.created_at,

                # ============================
                # Existing working fields
                # ============================
                "total_questions": total_questions,
                "total_points": float(test.total_points or 0),
                "passing_score": float(test.passing_score or 0),
                "start_time": test.start_time,
                "end_time": test.end_time,
                "attempts_count": attempts_count,
                "max_attempts": test.max_attempts,
                "can_attempt": can_attempt,
                "latest_attempt_status": latest['status'],
                "latest_attempt_score": float(latest['score'] or 0) if latest['score'] else None,
                "status": test.status
            })

    def get_test_summary(self, db: Session, test_id: UUID):
        """
        Get test summary with statistics
        """
        
        test = db.query(Test).filter(
            Test.id == test_id,
            Test.deleted_at.is_(None)
        ).first()
        
        if not test:
            raise HTTPException(404, "Test not found")
        
        # Count questions
        total_questions = (
            db.query(TestQuestion)
            .filter(TestQuestion.test_id == test_id)
            .count()
        )
        
        # Count attempts
        total_attempts = (
            db.query(TestAttempt)
            .filter(TestAttempt.test_id == test_id)
            .count()
        )
        
        # Count completed attempts
        completed_attempts = (
            db.query(TestAttempt)
            .filter(
                TestAttempt.test_id == test_id,
                TestAttempt.status.in_([AttemptStatus.GRADED, AttemptStatus.SUBMITTED])
            )
            .count()
        )
        
        # Calculate average score
        avg_score = (
            db.query(func.avg(TestAttempt.total_score))
            .filter(
                TestAttempt.test_id == test_id,
                TestAttempt.status == AttemptStatus.GRADED
            )
            .scalar()
        )
        
        # Calculate pass rate
        passed_count = (
            db.query(TestAttempt)
            .filter(
                TestAttempt.test_id == test_id,
                TestAttempt.passed == True
            )
            .count()
        )
        
        pass_rate = (
            round((passed_count / completed_attempts) * 100, 2)
            if completed_attempts > 0
            else 0
        )
        
        return {
            "id": test.id,
            "title": test.title,
            "description": test.description,
            "test_type": test.test_type.value if test.test_type else None,
            "status": test.status.value,
            "total_questions": total_questions,
            "total_points": float(test.total_points or 0),
            "time_limit_minutes": test.time_limit_minutes,
            "total_attempts": total_attempts,
            "completed_attempts": completed_attempts,
            "average_score": round(float(avg_score or 0), 2),
            "pass_rate": pass_rate,
            "created_at": test.created_at,
            "start_time": test.start_time,
            "end_time": test.end_time,
        }
    
    # ============================================================
    # LOAD STRUCTURE
    # ============================================================
    def _load_test_structure(self, db: Session, test_id: UUID, for_student: bool):
        """
        Load test structure với eager loading đầy đủ
        """
        query = (
            db.query(Test)
            .options(
                joinedload(Test.sections)
                .joinedload(TestSection.parts)
                .joinedload(TestSectionPart.passage),

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

                    # ================= OPTIONAL SORT =================
                    sorted_questions = sorted(
                        group.test_questions,
                        key=lambda tq: tq.group_order_number
                    )

                    for tq in sorted_questions:
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
                            "tags": qb.tags,

                            "points": int(tq.points or 0),
                            "order_number": tq.order_number,
                            "group_order_number": tq.group_order_number,  # ✅ FIX
                            "status": qb.status.value if hasattr(qb.status, 'value') else str(qb.status),
                            "visible_metadata": qb.extra_metadata,

                            "correct_answer": qb.correct_answer,
                            "rubric": qb.rubric,
                            "explanation": qb.explanation if hasattr(qb, 'explanation') else None,
                            "internal_metadata": qb.extra_metadata,
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

                # ================= FIX PASSAGE =================
                passage_data = None
                if part.passage:
                    passage_data = {
                        "id": part.passage.id,
                        "title": part.passage.title,
                        "text_content": part.passage.text_content,
                        "audio_url": part.passage.audio_url,
                        "image_url": part.passage.image_url,
                        "duration_seconds": part.passage.duration_seconds
                    }

                parts.append({
                    "id": part.id,
                    "name": part.name,
                    "order_number": part.order_number,
                    "passage": passage_data,  # ✅ FIX
                    "min_questions": part.min_questions,
                    "max_questions": part.max_questions,
                    "image_url": part.image_url,
                    "audio_url": part.audio_url,
                    "instructions": part.instructions,
                    "structure_part_id": part.structure_part_id,
                    "question_groups": groups
                })

            sections.append({
                "id": section.id,
                "name": section.name,
                "order_number": section.order_number,
                "skill_area": section.skill_area.value if section.skill_area else None,
                "time_limit_minutes": section.time_limit_minutes,
                "instructions": section.instructions,
                "structure_section_id": section.structure_section_id,
                "parts": parts
            })

        return {
            "id": test.id,
            "title": test.title,
            "description": test.description,
            "instructions": test.instructions,
            "test_type": test.test_type.value if test.test_type else "standard",
            "time_limit_minutes": test.time_limit_minutes,
            "total_points": float(test.total_points or 0),
            "passing_score": float(test.passing_score or 0),
            "max_attempts": test.max_attempts or 1,
            "randomize_questions": test.randomize_questions or False,
            "show_results_immediately": test.show_results_immediately or False,
            "start_time": test.start_time,
            "end_time": test.end_time,
            "status": test.status.value if hasattr(test.status, 'value') else str(test.status),
            "ai_grading_enabled": test.ai_grading_enabled or False,
            "created_by": test.created_by,
            "created_at": test.created_at,
            "updated_at": test.updated_at,
            "class_id": test.class_id,
            "course_id": test.course_id,
            "exam_type_id": test.exam_type_id,
            "structure_id": test.structure_id,
            "sections": sections
        }


test_service = TestService()
