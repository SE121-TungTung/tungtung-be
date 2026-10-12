import sys
import os
import json
import urllib.request
from decimal import Decimal

# Ensure app path is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import logging
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from app.core.database import SessionLocal
from app.models.user import User
from app.models.academic import Course
from app.models.test import (
    Test,
    TestSection,
    TestSectionPart,
    QuestionGroup,
    QuestionBank,
    TestQuestion,
    ContentPassage,
    TestStatus,
    TestType,
    QuestionType,
    SkillArea,
    DifficultyLevel,
    ContentStatus,
)

def cleanup_old_tests(db):
    """Clean up previous official practice tests if they exist"""
    old_tests = db.query(Test).filter(Test.title.like("IELTS Official Practice%")).all()
    for t in old_tests:
        print(f"[*] Removing existing test '{t.title}' for re-seed...")
        tqs = db.query(TestQuestion).filter(TestQuestion.test_id == t.id).all()
        q_ids = [tq.question_id for tq in tqs]
        for tq in tqs:
            db.delete(tq)
        db.flush()

        for q_id in q_ids:
            qb = db.query(QuestionBank).filter(QuestionBank.id == q_id).first()
            if qb:
                db.delete(qb)
        db.flush()

        for sec in t.sections:
            for part in sec.parts:
                for grp in part.question_groups:
                    db.delete(grp)
                db.flush()
                p_id = part.passage_id
                db.delete(part)
                db.flush()
                if p_id:
                    p = db.query(ContentPassage).filter(ContentPassage.id == p_id).first()
                    if p:
                        db.delete(p)
            db.delete(sec)
        db.delete(t)
    db.commit()

def fetch_json(url):
    print(f"[*] Downloading authentic IELTS data: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def seed_tests():
    db = SessionLocal()
    try:
        cleanup_old_tests(db)

        admin = db.query(User).filter(User.email == "admin@tungtung.edu.vn").first()
        if not admin:
            admin = db.query(User).first()

        course = db.query(Course).first()

        print(f"[*] Seeding IELTS Practice Tests using admin ID: {admin.id}")

        # =========================================================================
        # 1. AUTHENTIC LISTENING TEST (4 Parts, Real Audio, 40 Questions)
        # =========================================================================
        listening_url = "https://raw.githubusercontent.com/LuchoBazz/ielts-ai-dataset/main/datasets/practice-drills/listening/ielts-listening-band-8.0-test-001/manifest.json"
        l_data = fetch_json(listening_url)

        listening_title = "IELTS Official Practice - Listening Vol 1"
        test_listening = Test(
            title=listening_title,
            description="Đề thi luyện tập IELTS Listening đầy đủ 4 phần chuẩn format quốc tế với giọng đọc bản xứ thực tế và 40 câu hỏi Cambridge. Lượt làm bài không giới hạn.",
            instructions="Bài thi gồm 4 phần với 40 câu hỏi. Lắng nghe audio và trả lời các câu hỏi.",
            total_points=Decimal("40.0"),
            time_limit_minutes=40,
            passing_score=Decimal("20.0"),
            max_attempts=999,
            status=TestStatus.PUBLISHED,
            created_by=admin.id,
            course_id=course.id if course else None,
            test_type=TestType.IELTS_FULL,
            ai_grading_enabled=False,
            show_results_immediately=True,
        )
        db.add(test_listening)
        db.flush()

        sec_l = TestSection(
            test_id=test_listening.id,
            name="Listening Section",
            skill_area=SkillArea.LISTENING,
            order_number=1,
            time_limit_minutes=40,
            instructions="Listen to the recordings and answer the 40 questions.",
        )
        db.add(sec_l)
        db.flush()

        q_l_global = 1
        for s_idx, s in enumerate(l_data.get("sections", []), 1):
            audio_url = f"https://raw.githubusercontent.com/LuchoBazz/ielts-ai-dataset/main/datasets/practice-drills/listening/ielts-listening-band-8.0-test-001/section-{s_idx}.mp3"
            
            p_passage = ContentPassage(
                title=f"Part {s_idx}: {s.get('title', 'Listening Audio')}",
                content_type="listening_audio",
                audio_url=audio_url,
                text_content=s.get("transcript", ""),
                word_count=len(s.get("transcript", "").split()),
                status=ContentStatus.ACTIVE,
                created_by=admin.id,
            )
            db.add(p_passage)
            db.flush()

            part_l = TestSectionPart(
                test_section_id=sec_l.id,
                name=f"Part {s_idx}: {s.get('title', f'Part {s_idx}')}",
                order_number=s_idx,
                passage_id=p_passage.id,
                instructions="Listen carefully to the recording and answer questions for this part.",
                audio_url=audio_url,
                min_questions=10,
                max_questions=10,
            )
            db.add(part_l)
            db.flush()

            for g_idx, g in enumerate(s.get("question_groups", []), 1):
                raw_q_type = g.get("question_type", "sentence-completion")
                q_type = QuestionType.MULTIPLE_CHOICE if "multiple-choice" in raw_q_type else QuestionType.SENTENCE_COMPLETION

                q_group = QuestionGroup(
                    part_id=part_l.id,
                    name=f"Questions Group {g_idx}",
                    order_number=g_idx,
                    question_type=q_type,
                    instructions=g.get("instructions", "Answer the questions."),
                )
                db.add(q_group)
                db.flush()

                for local_idx, q in enumerate(g.get("questions", []), 1):
                    q_text = q.get("text") or q.get("stem") or f"Question {q_l_global}"
                    # Format blanks cleanly
                    if "sentence-completion" in raw_q_type:
                        q_text = q_text.replace("________", "[_______]").replace("______", "[_______]")
                        if "[_______]" not in q_text and "_" in q_text:
                            q_text = q_text.replace("_", "[_______]")

                    options = q.get("options")
                    ans = q.get("answer", "")

                    qb = QuestionBank(
                        title=f"Listening Q{q_l_global} - Part {s_idx}",
                        question_text=q_text,
                        question_type=q_type,
                        skill_area=SkillArea.LISTENING,
                        difficulty_level=DifficultyLevel.MEDIUM,
                        options=options,
                        correct_answer=ans,
                        audio_url=audio_url,
                        points=Decimal("1.0"),
                        status=ContentStatus.ACTIVE,
                        created_by=admin.id,
                    )
                    db.add(qb)
                    db.flush()

                    tq = TestQuestion(
                        test_id=test_listening.id,
                        question_id=qb.id,
                        group_id=q_group.id,
                        order_number=q_l_global,
                        group_order_number=local_idx,
                        points=Decimal("1.0"),
                        required=True,
                    )
                    db.add(tq)
                    q_l_global += 1

        print(f"[OK] Seeded Listening Test: '{listening_title}' with {q_l_global - 1} questions & real audio.")

        # =========================================================================
        # 2. AUTHENTIC READING TEST (3 Passages, 40 Questions)
        # =========================================================================
        reading_url = "https://raw.githubusercontent.com/LuchoBazz/ielts-ai-dataset/main/datasets/practice-drills/reading/ielts-reading-academic-band-8.0-test-001.json"
        r_data = fetch_json(reading_url)

        reading_title = "IELTS Official Practice - Reading Vol 1"
        test_reading = Test(
            title=reading_title,
            description="Đề thi luyện tập IELTS Academic Reading đầy đủ 3 bài đọc khoa học học thuật chuẩn format quốc tế. Lượt làm bài không giới hạn.",
            instructions="Bài thi gồm 3 bài đọc với 40 câu hỏi. Thời gian làm bài 60 phút.",
            total_points=Decimal("40.0"),
            time_limit_minutes=60,
            passing_score=Decimal("20.0"),
            max_attempts=999,
            status=TestStatus.PUBLISHED,
            created_by=admin.id,
            course_id=course.id if course else None,
            test_type=TestType.IELTS_FULL,
            ai_grading_enabled=False,
            show_results_immediately=True,
        )
        db.add(test_reading)
        db.flush()

        sec_r = TestSection(
            test_id=test_reading.id,
            name="Reading Section",
            skill_area=SkillArea.READING,
            order_number=1,
            time_limit_minutes=60,
            instructions="Read the passages and answer the 40 questions.",
        )
        db.add(sec_r)
        db.flush()

        q_r_global = 1
        for p_idx, p in enumerate(r_data.get("passages", []), 1):
            p_content = p.get("content", "")
            p_passage = ContentPassage(
                title=f"Passage {p_idx}: {p.get('title', '')}",
                content_type="reading_passage",
                text_content=p_content,
                word_count=len(p_content.split()),
                status=ContentStatus.ACTIVE,
                created_by=admin.id,
            )
            db.add(p_passage)
            db.flush()

            part_r = TestSectionPart(
                test_section_id=sec_r.id,
                name=f"Passage {p_idx}: {p.get('title', '')}",
                order_number=p_idx,
                passage_id=p_passage.id,
                instructions="You should spend about 20 minutes on this passage.",
                min_questions=13,
                max_questions=14,
            )
            db.add(part_r)
            db.flush()

            for g_idx, g in enumerate(p.get("question_groups", []), 1):
                raw_type = g.get("question_type", "multiple-choice")
                if "true-false" in raw_type:
                    q_type = QuestionType.TRUE_FALSE_NOT_GIVEN
                elif "yes-no" in raw_type:
                    q_type = QuestionType.YES_NO_NOT_GIVEN
                elif "heading" in raw_type:
                    q_type = QuestionType.MATCHING_HEADINGS
                elif "matching" in raw_type:
                    q_type = QuestionType.MATCHING_INFORMATION
                elif "summary" in raw_type:
                    q_type = QuestionType.SUMMARY_COMPLETION
                elif "table" in raw_type or "completion" in raw_type:
                    q_type = QuestionType.SENTENCE_COMPLETION
                elif "short-answer" in raw_type:
                    q_type = QuestionType.SHORT_ANSWER
                else:
                    q_type = QuestionType.MULTIPLE_CHOICE

                q_group = QuestionGroup(
                    part_id=part_r.id,
                    name=f"Questions Group {g_idx}",
                    order_number=g_idx,
                    question_type=q_type,
                    instructions=g.get("instructions", "Answer the questions according to the passage."),
                )
                db.add(q_group)
                db.flush()

                for local_idx, q in enumerate(g.get("questions", []), 1):
                    q_text = q.get("text") or q.get("stem") or f"Question {q_r_global}"
                    options = q.get("options")
                    ans = q.get("answer", "")

                    # Handle table completion rows if text is just Row X
                    if not ans and q.get("completion_gaps"):
                        gaps = [f"{g.get('gap_text')}: {g.get('answer')}" for g in q.get("completion_gaps") if g.get("answer")]
                        ans = ", ".join([g.get("answer") for g in q.get("completion_gaps") if g.get("answer")])
                        q_text = f"Fill the gaps for {q_text} in the mechanism records."

                    qb = QuestionBank(
                        title=f"Reading Q{q_r_global} - Passage {p_idx}",
                        question_text=q_text,
                        question_type=q_type,
                        skill_area=SkillArea.READING,
                        difficulty_level=DifficultyLevel.MEDIUM,
                        options=options,
                        correct_answer=str(ans) if ans else "Not Given",
                        points=Decimal("1.0"),
                        status=ContentStatus.ACTIVE,
                        created_by=admin.id,
                    )
                    db.add(qb)
                    db.flush()

                    tq = TestQuestion(
                        test_id=test_reading.id,
                        question_id=qb.id,
                        group_id=q_group.id,
                        order_number=q_r_global,
                        group_order_number=local_idx,
                        points=Decimal("1.0"),
                        required=True,
                    )
                    db.add(tq)
                    q_r_global += 1

        print(f"[OK] Seeded Reading Test: '{reading_title}' with {q_r_global - 1} questions.")

        # =========================================================================
        # 3. AUTHENTIC WRITING TEST (Task 1 Real Bar Chart + Task 2 Essay)
        # =========================================================================
        writing_title = "IELTS Official Practice - Writing Vol 1"
        test_writing = Test(
            title=writing_title,
            description="Đề thi luyện tập IELTS Academic Writing đầy đủ 2 phần Task 1 (Bar Chart) và Task 2 (Discursive Essay) chuẩn Cambridge.",
            instructions="Bài thi gồm 2 phần. Task 1 (tối thiểu 150 từ, 20 phút), Task 2 (tối thiểu 250 từ, 40 phút).",
            total_points=Decimal("9.0"),
            time_limit_minutes=60,
            passing_score=Decimal("5.0"),
            max_attempts=999,
            status=TestStatus.PUBLISHED,
            created_by=admin.id,
            course_id=course.id if course else None,
            test_type=TestType.IELTS_FULL,
            ai_grading_enabled=True,
            show_results_immediately=True,
        )
        db.add(test_writing)
        db.flush()

        sec_w = TestSection(
            test_id=test_writing.id,
            name="Writing Section",
            skill_area=SkillArea.WRITING,
            order_number=1,
            time_limit_minutes=60,
            instructions="Complete Task 1 and Task 2.",
        )
        db.add(sec_w)
        db.flush()

        # Task 1: Real IELTS Academic Bar Chart Image & Prompt
        task1_chart_image = "https://raw.githubusercontent.com/LuchoBazz/ielts-ai-dataset/main/datasets/synthetic-official-mocks/writing/ielts-writing-academic-001.jpeg"
        task1_prompt = """The bar chart below shows the percentage of electricity generated from renewable energy sources in four different countries between 2010 and 2020.

Summarise the information by selecting and reporting the main features, and make comparisons where relevant. Write at least 150 words."""

        p_w1 = ContentPassage(
            title="Task 1: Renewable Energy Production (2010 vs 2020)",
            content_type="reading_passage",
            text_content=task1_prompt,
            image_url=task1_chart_image,
            word_count=len(task1_prompt.split()),
            status=ContentStatus.ACTIVE,
            created_by=admin.id,
        )
        db.add(p_w1)
        db.flush()

        part_w1 = TestSectionPart(
            test_section_id=sec_w.id,
            name="Task 1: Academic Report (Chart)",
            order_number=1,
            passage_id=p_w1.id,
            image_url=task1_chart_image,
            instructions="You should spend about 20 minutes on this task. Write at least 150 words.",
            min_questions=1,
            max_questions=1,
        )
        db.add(part_w1)
        db.flush()

        g_w1 = QuestionGroup(
            part_id=part_w1.id,
            name="Task 1 Report",
            order_number=1,
            question_type=QuestionType.WRITING_TASK_1,
            instructions="Write at least 150 words.",
        )
        db.add(g_w1)
        db.flush()

        q_w1 = QuestionBank(
            title="Writing Task 1 - Renewable Energy Bar Chart",
            question_text=task1_prompt,
            question_type=QuestionType.WRITING_TASK_1,
            skill_area=SkillArea.WRITING,
            difficulty_level=DifficultyLevel.MEDIUM,
            image_url=task1_chart_image,
            points=Decimal("3.0"),
            status=ContentStatus.ACTIVE,
            created_by=admin.id,
        )
        db.add(q_w1)
        db.flush()

        tq_w1 = TestQuestion(
            test_id=test_writing.id,
            question_id=q_w1.id,
            group_id=g_w1.id,
            order_number=1,
            group_order_number=1,
            points=Decimal("3.0"),
            required=True,
        )
        db.add(tq_w1)

        # Task 2: Real IELTS Academic Essay Prompt
        task2_prompt = """Some people think that the most effective way to reduce traffic congestion in cities is to make public transport free. Others believe that charging drivers a heavy fee for entering city centres is a better solution.

Discuss both views and give your own opinion. Give reasons for your answer and include any relevant examples from your own knowledge or experience. Write at least 250 words."""

        p_w2 = ContentPassage(
            title="Task 2: Urban Traffic Solutions Discursive Essay",
            content_type="reading_passage",
            text_content=task2_prompt,
            word_count=len(task2_prompt.split()),
            status=ContentStatus.ACTIVE,
            created_by=admin.id,
        )
        db.add(p_w2)
        db.flush()

        part_w2 = TestSectionPart(
            test_section_id=sec_w.id,
            name="Task 2: Discursive Essay",
            order_number=2,
            passage_id=p_w2.id,
            instructions="You should spend about 40 minutes on this task. Write at least 250 words.",
            min_questions=1,
            max_questions=1,
        )
        db.add(part_w2)
        db.flush()

        g_w2 = QuestionGroup(
            part_id=part_w2.id,
            name="Task 2 Essay",
            order_number=1,
            question_type=QuestionType.WRITING_TASK_2,
            instructions="Write at least 250 words.",
        )
        db.add(g_w2)
        db.flush()

        q_w2 = QuestionBank(
            title="Writing Task 2 - Urban Traffic Solutions",
            question_text=task2_prompt,
            question_type=QuestionType.WRITING_TASK_2,
            skill_area=SkillArea.WRITING,
            difficulty_level=DifficultyLevel.HARD,
            points=Decimal("6.0"),
            status=ContentStatus.ACTIVE,
            created_by=admin.id,
        )
        db.add(q_w2)
        db.flush()

        tq_w2 = TestQuestion(
            test_id=test_writing.id,
            question_id=q_w2.id,
            group_id=g_w2.id,
            order_number=2,
            group_order_number=1,
            points=Decimal("6.0"),
            required=True,
        )
        db.add(tq_w2)

        print(f"[OK] Seeded Writing Test: '{writing_title}' with authentic Task 1 Chart and Task 2 Essay.")

        # =========================================================================
        # 4. SPEAKING TEST (3 Parts, Separated Individual Questions)
        # =========================================================================
        speaking_title = "IELTS Official Practice - Speaking Vol 1"
        test_speaking = Test(
            title=speaking_title,
            description="Đề thi luyện tập IELTS Speaking đầy đủ 3 phần chuẩn format quốc tế. Lượt làm bài không giới hạn.",
            instructions="Bài thi Nói gồm 3 phần: Part 1 (Phỏng vấn cá nhân), Part 2 (Thuyết trình Cue Card), Part 3 (Thảo luận sâu).",
            total_points=Decimal("9.0"),
            time_limit_minutes=15,
            passing_score=Decimal("5.0"),
            max_attempts=999,
            status=TestStatus.PUBLISHED,
            created_by=admin.id,
            course_id=course.id if course else None,
            test_type=TestType.IELTS_FULL,
            ai_grading_enabled=True,
            show_results_immediately=True,
        )
        db.add(test_speaking)
        db.flush()

        sec_s = TestSection(
            test_id=test_speaking.id,
            name="Speaking Section",
            skill_area=SkillArea.SPEAKING,
            order_number=1,
            time_limit_minutes=15,
            instructions="Complete the 3 Speaking parts by recording your answers.",
        )
        db.add(sec_s)
        db.flush()

        # Part 1: Introduction (4 separate questions)
        part_s1 = TestSectionPart(
            test_section_id=sec_s.id,
            name="Part 1: Introduction & Interview",
            order_number=1,
            instructions="The examiner will ask you general questions about yourself and familiar topics (4-5 minutes).",
            min_questions=4,
            max_questions=4,
        )
        db.add(part_s1)
        db.flush()

        g_s1 = QuestionGroup(
            part_id=part_s1.id,
            name="Part 1 Questions",
            order_number=1,
            question_type=QuestionType.SPEAKING_PART_1,
            instructions="Answer each question individually in 2-3 sentences.",
        )
        db.add(g_s1)
        db.flush()

        p1_speaking_prompts = [
            "Let's talk about your hometown. Where is your hometown located and what kind of place is it?",
            "What is the most interesting or memorable part of your hometown?",
            "How has your hometown changed significantly over the past five to ten years?",
            "Do you plan to continue living in your hometown in the future? Why or why not?",
        ]

        q_s_global = 1
        for local_idx, prompt in enumerate(p1_speaking_prompts, 1):
            qb = QuestionBank(
                title=f"Speaking Part 1 - Question {local_idx}",
                question_text=prompt,
                question_type=QuestionType.SPEAKING_PART_1,
                skill_area=SkillArea.SPEAKING,
                difficulty_level=DifficultyLevel.EASY,
                points=Decimal("0.75"),
                status=ContentStatus.ACTIVE,
                created_by=admin.id,
            )
            db.add(qb)
            db.flush()
            tq = TestQuestion(
                test_id=test_speaking.id,
                question_id=qb.id,
                group_id=g_s1.id,
                order_number=q_s_global,
                group_order_number=local_idx,
                points=Decimal("0.75"),
                required=True,
            )
            db.add(tq)
            q_s_global += 1

        # Part 2: Long Turn (Cue Card - 1 Question with 1 min prep, 2 min talk)
        part_s2 = TestSectionPart(
            test_section_id=sec_s.id,
            name="Part 2: Individual Long Turn (Cue Card)",
            order_number=2,
            instructions="You will be given a topic card. You have 1 minute to prepare and up to 2 minutes to speak.",
            min_questions=1,
            max_questions=1,
        )
        db.add(part_s2)
        db.flush()

        g_s2 = QuestionGroup(
            part_id=part_s2.id,
            name="Part 2 Cue Card",
            order_number=1,
            question_type=QuestionType.SPEAKING_PART_2,
            instructions="Read the cue card carefully. Prepare notes for 1 minute, then speak for up to 2 minutes.",
        )
        db.add(g_s2)
        db.flush()

        cue_card_prompt = """Describe an environmental project or initiative you participated in or heard about that made a positive difference.

You should say:
- What the project or initiative was
- Who organized or participated in it
- What specific actions were taken
- And explain why you felt this initiative was successful or inspiring."""

        qb_s2 = QuestionBank(
            title="Speaking Part 2 - Environmental Initiative",
            question_text=cue_card_prompt,
            question_type=QuestionType.SPEAKING_PART_2,
            skill_area=SkillArea.SPEAKING,
            difficulty_level=DifficultyLevel.MEDIUM,
            points=Decimal("3.0"),
            status=ContentStatus.ACTIVE,
            created_by=admin.id,
        )
        db.add(qb_s2)
        db.flush()

        tq_s2 = TestQuestion(
            test_id=test_speaking.id,
            question_id=qb_s2.id,
            group_id=g_s2.id,
            order_number=q_s_global,
            group_order_number=1,
            points=Decimal("3.0"),
            required=True,
        )
        db.add(tq_s2)
        q_s_global += 1

        # Part 3: Two-way Discussion (4 separate questions)
        part_s3 = TestSectionPart(
            test_section_id=sec_s.id,
            name="Part 3: Two-way Discussion",
            order_number=3,
            instructions="The examiner will ask further questions connected to the topic in Part 2 (4-5 minutes).",
            min_questions=4,
            max_questions=4,
        )
        db.add(part_s3)
        db.flush()

        g_s3 = QuestionGroup(
            part_id=part_s3.id,
            name="Part 3 Discussion Questions",
            order_number=1,
            question_type=QuestionType.SPEAKING_PART_3,
            instructions="Discuss the broader issues in depth with reasoned arguments and examples.",
        )
        db.add(g_s3)
        db.flush()

        p3_speaking_prompts = [
            "Do you think individual actions like recycling make a meaningful difference compared to government regulation?",
            "How can schools encourage children to develop environmentally conscious habits early in life?",
            "In your opinion, will future technology be able to reverse environmental damage, or must human consumption habits change fundamentally?",
            "To what extent should wealthier countries assist developing nations in adopting green technologies?",
        ]

        for local_idx, prompt in enumerate(p3_speaking_prompts, 1):
            qb = QuestionBank(
                title=f"Speaking Part 3 - Question {local_idx}",
                question_text=prompt,
                question_type=QuestionType.SPEAKING_PART_3,
                skill_area=SkillArea.SPEAKING,
                difficulty_level=DifficultyLevel.HARD,
                points=Decimal("0.75"),
                status=ContentStatus.ACTIVE,
                created_by=admin.id,
            )
            db.add(qb)
            db.flush()
            tq = TestQuestion(
                test_id=test_speaking.id,
                question_id=qb.id,
                group_id=g_s3.id,
                order_number=q_s_global,
                group_order_number=local_idx,
                points=Decimal("0.75"),
                required=True,
            )
            db.add(tq)
            q_s_global += 1

        print(f"[OK] Seeded Speaking Test: '{speaking_title}' with 3 Parts, {q_s_global - 1} separated questions.")

        db.commit()
        print("\n=======================================================")
        print("[SUCCESS] All 4 official IELTS practice tests seeded with real exam format!")
        print(" - Listening: 40 questions (Commercial Freight, Airport T3, Marine Biology, Global Supply Chains) with real audio files")
        print(" - Reading: 40 questions (Antikythera Mechanism, Soil Microbiomes, Conscious Will) with 3 full passages")
        print(" - Writing: 2 Tasks (Task 1 Real Bar Chart diagram image + Task 2 Traffic Congestion Essay)")
        print(" - Speaking: 9 separated questions (Part 1 [4 Qs] + Part 2 Cue card + Part 3 [4 Qs])")
        print(" - All tests have max_attempts=999 for unlimited practice testing.")
        print("=======================================================\n")

    except Exception as e:
        db.rollback()
        print(f"[ERR] Seeding failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    seed_tests()
