import sys
import os
import json
import uuid

# Multilevel import fallback
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.test import (
    Test, TestSection, TestSectionPart, QuestionGroup, QuestionBank, TestQuestion,
    ContentPassage, SkillArea, DifficultyLevel, QuestionType, TestType, TestStatus, ContentStatus
)
from app.models.user import User, UserRole

def seed_crawled_data():
    db = SessionLocal()
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "crawled_data")
    
    print("[INFO] Bat dau nap du lieu da cao vao Database PostgreSQL...")

    # Find admin or any existing user
    user = db.query(User).filter(User.role == UserRole.SYSTEM_ADMIN).first() or db.query(User).first()
    if not user:
        print("[ERROR] Khong tim thay User trong Database. Vui long chay seed_data.py truoc.")
        return
    user_id = user.id

    # 1. SEED READING TESTS
    reading_json_path = os.path.join(data_dir, "ielts_reading_crawled.json")
    if os.path.exists(reading_json_path):
        with open(reading_json_path, "r", encoding="utf-8") as f:
            reading_data = json.load(f)

        print(f"\n--- Dang nap {len(reading_data)} de Reading vao DB ---")
        for item in reading_data:
            try:
                # Create Passage
                passage = ContentPassage(
                    id=uuid.uuid4(),
                    title=item["title"],
                    content_type="reading_passage",
                    text_content=item["passage_text"],
                    difficulty_level=DifficultyLevel.MEDIUM,
                    word_count=len(item["passage_text"].split()),
                    status=ContentStatus.ACTIVE,
                    created_by=user_id
                )
                db.add(passage)
                db.flush()

                # Create Test
                test = Test(
                    id=uuid.uuid4(),
                    title=f"Reading Practice: {item['title'][:50]}",
                    description=f"Bai thuc hanh IELTS Reading: {item['title']}",
                    time_limit_minutes=20,
                    passing_score=60,
                    status=TestStatus.PUBLISHED,
                    test_type=TestType.PRACTICE if hasattr(TestType, 'PRACTICE') else TestType.IELTS_FULL,
                    created_by=user_id
                )
                db.add(test)
                db.flush()

                # Create Section
                section = TestSection(
                    id=uuid.uuid4(),
                    test_id=test.id,
                    name="Reading Section",
                    skill_area=SkillArea.READING,
                    order_number=1,
                    time_limit_minutes=20
                )
                db.add(section)
                db.flush()

                # Create Part
                part = TestSectionPart(
                    id=uuid.uuid4(),
                    test_section_id=section.id,
                    name="Passage 1",
                    order_number=1,
                    passage_id=passage.id
                )
                db.add(part)
                db.flush()

                # Create Question Group & Questions
                for q_group_item in item.get("question_groups", []):
                    q_group = QuestionGroup(
                        id=uuid.uuid4(),
                        part_id=part.id,
                        name=f"Group {q_group_item['order']}",
                        order_number=q_group_item["order"],
                        question_type=QuestionType.TRUE_FALSE_NOT_GIVEN
                    )
                    db.add(q_group)
                    db.flush()

                    # Create a sample Question in Bank
                    qb = QuestionBank(
                        id=uuid.uuid4(),
                        title=f"{item['title'][:30]} Q{q_group_item['order']}",
                        question_text=q_group_item["raw_content"][:300] or "Do the statements agree with the information?",
                        question_type=QuestionType.TRUE_FALSE_NOT_GIVEN,
                        skill_area=SkillArea.READING,
                        difficulty_level=DifficultyLevel.MEDIUM,
                        correct_answer="TRUE",
                        points=1,
                        status=ContentStatus.ACTIVE,
                        created_by=user_id
                    )
                    db.add(qb)
                    db.flush()

                    tq = TestQuestion(
                        id=uuid.uuid4(),
                        test_id=test.id,
                        question_id=qb.id,
                        group_id=q_group.id,
                        order_number=q_group_item["order"],
                        group_order_number=1,
                        points=1
                    )
                    db.add(tq)

                db.commit()
                print(f"  [DB] SUCCESS: Nap thanh cong {item['title'][:30]}")
            except Exception as e:
                db.rollback()
                print(f"  [DB] ERROR: Loi nap bai {item['title'][:30]}: {e}")

    # 2. SEED WRITING TESTS
    writing_json_path = os.path.join(data_dir, "ielts_writing_crawled.json")
    if os.path.exists(writing_json_path):
        with open(writing_json_path, "r", encoding="utf-8") as f:
            writing_data = json.load(f)

        print(f"\n--- Dang nap {len(writing_data)} de Writing vao DB ---")
        for item in writing_data:
            try:
                q_type = QuestionType.WRITING_TASK_1 if item["task_type"] == "writing_task_1" else QuestionType.WRITING_TASK_2
                time_limit = 20 if item["task_type"] == "writing_task_1" else 40

                test = Test(
                    id=uuid.uuid4(),
                    title=item["title"],
                    description=item["prompt"],
                    time_limit_minutes=time_limit,
                    passing_score=60,
                    status=TestStatus.PUBLISHED,
                    ai_grading_enabled=True,
                    created_by=user_id
                )
                db.add(test)
                db.flush()

                section = TestSection(
                    id=uuid.uuid4(),
                    test_id=test.id,
                    name="Writing Section",
                    skill_area=SkillArea.WRITING,
                    order_number=1,
                    time_limit_minutes=time_limit
                )
                db.add(section)
                db.flush()

                part = TestSectionPart(
                    id=uuid.uuid4(),
                    test_section_id=section.id,
                    name=item["title"],
                    order_number=1,
                    image_url=item.get("image_url")
                )
                db.add(part)
                db.flush()

                q_group = QuestionGroup(
                    id=uuid.uuid4(),
                    part_id=part.id,
                    name="Task Prompt",
                    order_number=1,
                    question_type=q_type,
                    image_url=item.get("image_url")
                )
                db.add(q_group)
                db.flush()

                qb = QuestionBank(
                    id=uuid.uuid4(),
                    title=item["title"],
                    question_text=item["prompt"],
                    question_type=q_type,
                    skill_area=SkillArea.WRITING,
                    difficulty_level=DifficultyLevel.MEDIUM,
                    image_url=item.get("image_url"),
                    points=9,
                    status=ContentStatus.ACTIVE,
                    created_by=user_id
                )
                db.add(qb)
                db.flush()

                tq = TestQuestion(
                    id=uuid.uuid4(),
                    test_id=test.id,
                    question_id=qb.id,
                    group_id=q_group.id,
                    order_number=1,
                    group_order_number=1,
                    points=9
                )
                db.add(tq)
                db.commit()
                print(f"  [DB] SUCCESS: Nap thành cong Writing {item['title']}")
            except Exception as e:
                db.rollback()
                print(f"  [DB] ERROR: Loi nap Writing {item['title']}: {e}")

    print("\n[COMPLETE] Da hoan thanh nap toan bo du lieu de thi vao Database!")

if __name__ == "__main__":
    seed_crawled_data()
