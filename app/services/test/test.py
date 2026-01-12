from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case
from uuid import UUID
from fastapi import HTTPException
from typing import Optional, List
from datetime import datetime

from app.schemas.test.test_create import TestCreate
from app.schemas.test.test_read import TestResponse, TestTeacherResponse, TestListResponse, TestListPageResponse
from app.models.test import ContentPassage

from app.services.audit_log import audit_service
from app.models.audit_log import AuditAction

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
from app.schemas.test.test_create import TestUpdate
from datetime import datetime, timezone

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
                    u_type = UploadType.AUDIO
                    if file.filename and ("image" in file.filename.lower() or any(ext in file.filename.lower() for ext in ['.jpg', '.png', '.jpeg'])):
                        u_type = UploadType.IMAGE
                    file_meta = await upload_and_save_metadata(
                        db=db,
                        uploaded_file=file,
                        user_id=created_by,
                        folder="test_material",
                        upload_type_value=u_type,
                        access_level_value=AccessLevel.PUBLIC
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
                        print(f"File {filename} not found in upload map")
                        return None
                    return uploaded_map[filename]
                return url
            
            total_points = sum(
                q.points for sec in data.sections 
                for part in sec.parts 
                for group in part.question_groups 
                for q in group.questions
            )

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
                total_points=total_points,
                created_by=created_by,
                status=data.status
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

            audit_service.log(
                db=db,
                user_id=created_by,
                action=AuditAction.CREATE,
                table_name="tests",
                record_id=test.id,
                new_values={
                    "title": test.title,
                    "description": test.description,
                    "class_id": str(test.class_id)
                }
            )

            db.commit()
            db.refresh(test)

            return test
        except HTTPException as httpex:
            db.rollback()
            raise httpex
        except Exception as e:
            db.rollback()
            raise HTTPException(500, detail=str(e))

    async def update_test(
        self,
        db: Session,
        test_id: UUID,
        payload: TestUpdate,
        user_id: UUID,
        files: Optional[List[UploadFile]] = None
    ):
        
        uploaded_map = {}

        if files:
            for file in files:
                u_type = UploadType.AUDIO
                if file.filename and any(ext in file.filename.lower() for ext in ['.jpg', '.png', '.jpeg']):
                    u_type = UploadType.IMAGE

                file_meta = await upload_and_save_metadata(
                    db=db,
                    uploaded_file=file,
                    user_id=user_id,
                    folder="test_material",
                    upload_type_value=u_type,
                    access_level_value=AccessLevel.PUBLIC
                )

                if not file_meta or not file_meta.file_path:
                    raise HTTPException(500, f"Upload failed for file {file.filename}")

                uploaded_map[file.filename] = file_meta.file_path


        def resolve_url(url: Optional[str]) -> Optional[str]:
            if not url:
                return None
            if url.startswith("file:"):
                filename = url.replace("file:", "")
                return uploaded_map.get(filename)
            return url


        test = self.get_test_by_id(db, test_id) # Tận dụng hàm get có sẵn để check 404/Deleted

        # Convert payload sang dict, loại bỏ các trường None
        update_data = payload.model_dump(exclude_unset=True)

        # --- LOGIC 1: CHẶN PUBLISH TẠI HÀM NÀY ---
        # Nếu muốn Publish, phải gọi route /publish riêng để validate dữ liệu
        if update_data.get("status") == TestStatus.PUBLISHED:
             raise HTTPException(
                400, 
                "To publish a test, please use the 'Publish' endpoint."
            )

        # --- LOGIC 2: CHECK KHI UN-PUBLISH (Về Draft) ---
        # Nếu đang Published mà muốn về Draft -> Phải check xem có ai thi chưa
        if (
            test.status == TestStatus.PUBLISHED 
            and update_data.get("status") == TestStatus.DRAFT
        ):
            has_attempt = db.query(TestAttempt).filter(TestAttempt.test_id == test.id).first()
            if has_attempt:
                raise HTTPException(400, "Cannot unpublish (set to Draft) a test that already has student attempts.")

        # --- LOGIC 3: UPDATE DỮ LIỆU ---
        update_data = payload.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            if field in ("audio_url", "image_url"):
                value = resolve_url(value)

            setattr(test, field, value)


        test.updated_by = user_id
        
        # Ghi Audit Log
        audit_service.log(
            db=db,
            user_id=user_id,
            action=AuditAction.UPDATE,
            table_name="tests",
            record_id=test.id,
            new_values=update_data
        )

        db.commit()
        db.refresh(test)
        return test

    def publish_test(self, db: Session, test_id: UUID, user_id: UUID):
        """
        Chuyên dùng để Public test.
        Tại đây sẽ validate kỹ càng trước khi cho phép Public.
        """
        test = self.get_test_by_id(db, test_id) # Hàm này nên join sẵn questions/sections

        if test.status == TestStatus.PUBLISHED:
            raise HTTPException(400, "Test is already published")

        # --- VALIDATION LOGIC ---
        # 1. Check câu hỏi
        if not test.questions: 
            # Lưu ý: test.test_questions là relation 1-N
            raise HTTPException(400, "Cannot publish a test with no questions")

        # 2. Check tổng điểm (Ví dụ phải >= 1)
        total_points = sum(tq.points for tq in test.questions)
        if total_points <= 0:
             raise HTTPException(400, "Total points of the test must be greater than 0")
        
        # 3. Check thời gian
        if not test.time_limit_minutes or test.time_limit_minutes <= 0:
            raise HTTPException(400, "Test duration must be set")

        # --- ACTION ---
        old_status = test.status
        test.status = TestStatus.PUBLISHED
        test.updated_by = user_id

        audit_service.log(
            db=db,
            user_id=user_id,
            action=AuditAction.UPDATE,
            table_name="tests",
            record_id=test.id,
            new_values={"status": "PUBLISHED", "old_status": str(old_status)}
        )

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
        try:
            # ============================================================
            # 1. BASE QUERY (NO JOIN)
            # ============================================================
            base_query = db.query(Test).filter(Test.deleted_at.is_(None))

            if class_id:
                base_query = base_query.filter(Test.class_id == class_id)

            if status:
                base_query = base_query.filter(Test.status == status)

            if skill:
                base_query = base_query.filter(
                    Test.id.in_(
                        db.query(TestSection.test_id)
                        .filter(TestSection.skill_area == skill)
                    )
                )

            # ============================================================
            # 2. TOTAL COUNT
            # ============================================================
            total = base_query.count()

            # ============================================================
            # 3. DATA QUERY
            # ============================================================
            tests = (
                base_query
                .options(
                    joinedload(Test.sections),
                    joinedload(Test.questions)
                )
                .order_by(Test.created_at.desc())
                .offset(skip)
                .limit(limit)
                .all()
            )

            if not tests:
                return {
                    "total": total,
                    "skip": skip,
                    "limit": limit,
                    "tests": []
                }

            test_ids = [t.id for t in tests]

            # ============================================================
            # 4. BATCH ATTEMPT STATS
            # ============================================================
            attempt_rows = (
                db.query(
                    TestAttempt.test_id,
                    func.count(TestAttempt.id).label("total_attempts"),
                    func.sum(
                        case(
                            (TestAttempt.status == AttemptStatus.SUBMITTED, 1),
                            else_=0
                        )
                    ).label("pending_attempts")
                )
                .filter(TestAttempt.test_id.in_(test_ids))
                .group_by(TestAttempt.test_id)
                .all()
            )

            attempts_map = {
                r.test_id: {
                    "total": r.total_attempts,
                    "pending": r.pending_attempts or 0
                }
                for r in attempt_rows
            }

            # ============================================================
            # 5. BUILD RESPONSE
            # ============================================================
            results = []

            for test in tests:
                skill_area = (
                    test.sections[0].skill_area
                    if test.sections
                    else SkillArea.READING
                )

                attempt_info = attempts_map.get(
                    test.id,
                    {"total": 0, "pending": 0}
                )

                results.append({
                    "id": test.id,
                    "title": test.title,
                    "description": test.description,
                    "skill": skill_area,
                    "difficulty": DifficultyLevel.MEDIUM,
                    "test_type": test.test_type,
                    "duration_minutes": test.time_limit_minutes or 0,
                    "total_questions": len(test.questions),
                    "created_at": test.created_at,
                    "pending_attempts_count": attempt_info["pending"],
                    "total_attempts_count": attempt_info["total"],
                })

            return {
                "total": total,
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
        try:
            now = datetime.now(timezone.utc)

            # ============================================================
            # 1. BASE QUERY
            # ============================================================
            base_query = (
                db.query(Test)
                .filter(
                    Test.deleted_at.is_(None),
                    Test.status == TestStatus.PUBLISHED,
                    (Test.start_time.is_(None)) | (Test.start_time <= now),
                    (Test.end_time.is_(None)) | (Test.end_time >= now),
                )
            )

            if class_id:
                base_query = base_query.filter(Test.class_id == class_id)

            if skill:
                base_query = base_query.filter(
                    Test.id.in_(
                        db.query(TestSection.test_id)
                        .filter(TestSection.skill_area == skill)
                    )
                )

            # ============================================================
            # 2. TOTAL
            # ============================================================
            total = base_query.count()

            # ============================================================
            # 3. DATA QUERY
            # ============================================================
            tests = (
                base_query
                .options(
                    joinedload(Test.sections),
                    joinedload(Test.questions)
                )
                .order_by(
                    Test.start_time.desc().nullslast(),
                    Test.created_at.desc()
                )
                .offset(skip)
                .limit(limit)
                .all()
            )

            if not tests:
                return {
                    "total": total,
                    "skip": skip,
                    "limit": limit,
                    "tests": []
                }

            test_ids = [t.id for t in tests]

            # ============================================================
            # 4. BATCH ATTEMPTS PER STUDENT
            # ============================================================
            attempt_rows = (
                db.query(
                    TestAttempt.test_id,
                    func.count(TestAttempt.id).label("attempts_count"),
                    func.max(TestAttempt.attempt_number).label("max_attempt")
                )
                .filter(
                    TestAttempt.test_id.in_(test_ids),
                    TestAttempt.student_id == student_id
                )
                .group_by(TestAttempt.test_id)
                .all()
            )

            attempts_map = {
                r.test_id: {
                    "count": r.attempts_count,
                    "max_attempt": r.max_attempt or 0
                }
                for r in attempt_rows
            }

            # ============================================================
            # 5. BUILD RESPONSE
            # ============================================================
            results = []

            for test in tests:
                skill_area = (
                    test.sections[0].skill_area
                    if test.sections
                    else SkillArea.READING
                )

                attempt_info = attempts_map.get(
                    test.id,
                    {"count": 0, "max_attempt": 0}
                )

                max_attempts = test.max_attempts or 1
                can_attempt = attempt_info["count"] < max_attempts

                results.append({
                    "id": test.id,
                    "title": test.title,
                    "description": test.description,
                    "skill": skill_area,
                    "difficulty": DifficultyLevel.MEDIUM,
                    "test_type": test.test_type.value if test.test_type else None,
                    "time_limit_minutes": test.time_limit_minutes,
                    "total_questions": len(test.questions),
                    "total_points": float(test.total_points or 0),
                    "passing_score": float(test.passing_score or 0),
                    "attempts_count": attempt_info["count"],
                    "max_attempts": max_attempts,
                    "can_attempt": can_attempt,
                    "status": test.status,
                })

            return {
                "total": total,
                "skip": skip,
                "limit": limit,
                "tests": results
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

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
                .joinedload(TestSectionPart.passage),  # ✅ FIX

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

    def get_test_by_id(self, db: Session, test_id: UUID) -> Test:
        """
        Lấy thông tin Test và preload các thông tin quan trọng 
        để phục vụ validation (questions, sections).
        """
        test = (
            db.query(Test)
            # Quan trọng: Load sẵn test_questions để tính tổng điểm ở hàm publish_test
            .options(
                joinedload(Test.questions),
                joinedload(Test.sections) 
            )
            .filter(
                Test.id == test_id,
                Test.deleted_at.is_(None)
            )
            .first()
        )

        if not test:
            raise HTTPException(status_code=404, detail="Test not found")

        return test

test_service = TestService()
