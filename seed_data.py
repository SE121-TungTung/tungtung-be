import sys
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models import (
    User, Room, Course, Class, ClassEnrollment, ClassSession, AttendanceRecord,
    Test, TestAttempt, QuestionBank, TestQuestion, QuestionGroup, TestSection, TestSectionPart,
    KPITemplate, KPITemplateMetric, KPIPeriod, KPIRecord, KPIMetricResult,
    TeacherPayrollConfig, Salary, SalaryAdjustment
)
from app.models.user import UserRole, UserStatus
from app.models.academic import RoomType, RoomStatus, CourseLevel, CourseType, CourseStatus, ClassStatus, PaymentStatus, EnrollmentStatus
from app.models.session_attendance import SessionStatus, AttendanceStatus
from app.models.test import TestStatus, TestType, AttemptStatus, QuestionType, SkillArea, DifficultyLevel, ContentStatus
from app.models.kpi import ContractType, BonusType, MetricUnit, ApprovalStatus, DataSource, PeriodType, SalaryStatus, AdjustmentType

def clean_database(db: Session):
    print("Cleaning database...")
    tables_to_truncate = [
        "salary_adjustments", "salaries", "kpi_disputes", "support_calc_entries",
        "kpi_approval_logs", "kpi_metric_results", "kpi_records", "kpi_periods",
        "kpi_template_metrics", "kpi_templates", "teacher_payroll_configs",
        "attendance_records", "class_sessions", "class_enrollments",
        "test_responses", "test_attempts", "test_questions", "question_groups",
        "test_section_parts", "test_sections", "tests", "question_bank",
        "content_passages", "classes", "courses", "rooms", "users", "password_reset_otps",
        "recommendation_logs", "certificates", "substitution_requests", "chatbot_documents"
    ]
    for table in tables_to_truncate:
        try:
            db.execute(text(f"TRUNCATE TABLE {table} CASCADE;"))
            db.commit()
            print(f" - Truncated table: {table}")
        except Exception as e:
            db.rollback()
            print(f" - Error truncating table {table} (might not exist): {e}")

def seed_data():
    db = SessionLocal()
    try:
        # 1. Clean old dirty data
        clean_database(db)
        print("\nStarting seeding realistic data...")

        # 2. Hashed Password for all seeded users
        shared_password_hash = get_password_hash("Password123")
        print("Generated shared password hash for all users: Password123")

        # 3. Create Users
        print("Seeding Users...")
        users_data = [
            # Admins
            {"email": "admin@tungtung.edu.vn", "role": UserRole.CENTER_ADMIN, "first_name": "Hoàng", "last_name": "Lê Minh", "phone": "0912345678"},
            {"email": "vanphong1@tungtung.edu.vn", "role": UserRole.OFFICE_ADMIN, "first_name": "Mai", "last_name": "Nguyễn Thị", "phone": "0987654321"},
            {"email": "vanphong2@tungtung.edu.vn", "role": UserRole.OFFICE_ADMIN, "first_name": "Nam", "last_name": "Trần Đức", "phone": "0911223344"},
            # Teachers
            {"email": "teacher.an@tungtung.edu.vn", "role": UserRole.TEACHER, "first_name": "An", "last_name": "Trần Thanh", "phone": "0901234567"},
            {"email": "teacher.binh@tungtung.edu.vn", "role": UserRole.TEACHER, "first_name": "Bình", "last_name": "Lê Văn", "phone": "0902345678"},
            {"email": "teacher.chi@tungtung.edu.vn", "role": UserRole.TEACHER, "first_name": "Chi", "last_name": "Phạm Minh", "phone": "0903456789"},
            {"email": "teacher.dung@tungtung.edu.vn", "role": UserRole.TEACHER, "first_name": "Dũng", "last_name": "Vũ Quốc", "phone": "0904567890"},
            # TAs
            {"email": "ta.giang@tungtung.edu.vn", "role": UserRole.TA, "first_name": "Giang", "last_name": "Nguyễn Hương", "phone": "0905678901"},
            {"email": "ta.hai@tungtung.edu.vn", "role": UserRole.TA, "first_name": "Hải", "last_name": "Trần Minh", "phone": "0906789012"},
            # Students
            {"email": "student.minh@gmail.com", "role": UserRole.STUDENT, "first_name": "Minh", "last_name": "Phan Duy", "phone": "0971112222"},
            {"email": "student.khoi@gmail.com", "role": UserRole.STUDENT, "first_name": "Khôi", "last_name": "Lưu Minh", "phone": "0972223333"},
            {"email": "student.an@gmail.com", "role": UserRole.STUDENT, "first_name": "An", "last_name": "Nguyễn Văn", "phone": "0973334444"},
            {"email": "student.binh@gmail.com", "role": UserRole.STUDENT, "first_name": "Bình", "last_name": "Trần Thị", "phone": "0974445555"},
            {"email": "student.cuong@gmail.com", "role": UserRole.STUDENT, "first_name": "Cường", "last_name": "Lê Quốc", "phone": "0975556666"},
            {"email": "student.dung@gmail.com", "role": UserRole.STUDENT, "first_name": "Dũng", "last_name": "Phạm Tiến", "phone": "0976667777"},
            {"email": "student.huong@gmail.com", "role": UserRole.STUDENT, "first_name": "Hương", "last_name": "Hoàng Thu", "phone": "0977778888"},
            {"email": "student.lan@gmail.com", "role": UserRole.STUDENT, "first_name": "Lan", "last_name": "Ngô Thị", "phone": "0978889999"},
            {"email": "student.nam@gmail.com", "role": UserRole.STUDENT, "first_name": "Nam", "last_name": "Vũ Hoài", "phone": "0979990000"},
            {"email": "student.vy@gmail.com", "role": UserRole.STUDENT, "first_name": "Vy", "last_name": "Đỗ Khánh", "phone": "0970001111"}
        ]
        
        users_map = {}
        for u in users_data:
            user = User(
                email=u["email"],
                password_hash=shared_password_hash,
                role=u["role"],
                status=UserStatus.ACTIVE,
                first_name=u["first_name"],
                last_name=u["last_name"],
                phone=u["phone"],
                date_of_birth=date(2000, 1, 1),
                address="Hồ Chí Minh, Việt Nam",
                is_first_login=False,
                must_change_password=False
            )
            db.add(user)
            db.flush()
            users_map[u["email"]] = user
        
        # 4. Create Rooms
        print("Seeding Rooms...")
        rooms_data = [
            {"name": "Room 101", "capacity": 20, "type": RoomType.CLASSROOM},
            {"name": "Room 102", "capacity": 25, "type": RoomType.CLASSROOM},
            {"name": "Lab 201", "capacity": 30, "type": RoomType.COMPUTER_LAB},
            {"name": "Room 103", "capacity": 20, "type": RoomType.CLASSROOM}
        ]
        rooms_map = {}
        for r in rooms_data:
            room = Room(
                name=r["name"],
                capacity=r["capacity"],
                room_type=r["type"],
                status=RoomStatus.AVAILABLE,
                location="Khu A - Tầng 1" if "10" in r["name"] else "Khu B - Tầng 2",
                notes="Trang bị đầy đủ điều hòa, tivi, bảng từ"
            )
            db.add(room)
            db.flush()
            rooms_map[r["name"]] = room

        # 5. Create Courses
        print("Seeding Courses...")
        courses_data = [
            {"name": "IELTS Foundation", "level": CourseLevel.ELEMENTARY, "type": CourseType.IELTS, "fee": 4500000, "duration": 60},
            {"name": "IELTS Intensive", "level": CourseLevel.UPPER_INTERMEDIATE, "type": CourseType.IELTS, "fee": 6800000, "duration": 80},
            {"name": "General English A2", "level": CourseLevel.ELEMENTARY, "type": CourseType.GENERAL_ENGLISH, "fee": 3000000, "duration": 48},
            {"name": "Business Communication", "level": CourseLevel.INTERMEDIATE, "type": CourseType.BUSINESS, "fee": 5500000, "duration": 50}
        ]
        courses_map = {}
        for c in courses_data:
            course = Course(
                name=c["name"],
                description=f"Khóa học {c['name']} chuẩn đầu ra chất lượng cao.",
                level=c["level"],
                course_type=c["type"],
                duration_hours=c["duration"],
                max_students=25,
                min_students=5,
                fee_amount=Decimal(c["fee"]),
                currency="VND",
                syllabus={"chapters": ["Bài mở đầu", "Phát triển kỹ năng", "Kiểm tra giữa kỳ", "Luyện đề", "Tổng kết khóa học"]},
                learning_objectives=[f"Đạt được kỹ năng tối thiểu tương ứng với {c['name']}", "Giao tiếp tự tin trôi chảy"],
                prerequisites=["Đạt bài test đầu vào"],
                status=CourseStatus.ACTIVE
            )
            db.add(course)
            db.flush()
            courses_map[c["name"]] = course

        # 6. Create Classes
        print("Seeding Classes...")
        classes_data = [
            {"name": "IELTS-FD-01", "course": "IELTS Foundation", "teacher": "teacher.an@tungtung.edu.vn", "ta": "ta.giang@tungtung.edu.vn", "room": "Room 101", "start": date(2026, 5, 1), "end": date(2026, 8, 1), "fee": 4500000, "status": ClassStatus.ACTIVE},
            {"name": "IELTS-IT-01", "course": "IELTS Intensive", "teacher": "teacher.binh@tungtung.edu.vn", "ta": "ta.hai@tungtung.edu.vn", "room": "Lab 201", "start": date(2026, 5, 15), "end": date(2026, 9, 15), "fee": 6800000, "status": ClassStatus.ACTIVE},
            {"name": "GE-A2-01", "course": "General English A2", "teacher": "teacher.chi@tungtung.edu.vn", "ta": None, "room": "Room 102", "start": date(2026, 6, 1), "end": date(2026, 8, 15), "fee": 3000000, "status": ClassStatus.ACTIVE},
            {"name": "BIZ-COM-01", "course": "Business Communication", "teacher": "teacher.dung@tungtung.edu.vn", "ta": None, "room": "Room 103", "start": date(2026, 7, 1), "end": date(2026, 9, 15), "fee": 5500000, "status": ClassStatus.SCHEDULED}
        ]
        
        classes_map = {}
        for cl in classes_data:
            c_obj = courses_map[cl["course"]]
            t_obj = users_map[cl["teacher"]]
            ta_obj = users_map[cl["ta"]] if cl["ta"] else None
            r_obj = rooms_map[cl["room"]]
            
            clazz = Class(
                name=cl["name"],
                course_id=c_obj.id,
                teacher_id=t_obj.id,
                ta_id=ta_obj.id if ta_obj else None,
                room_id=r_obj.id,
                start_date=cl["start"],
                end_date=cl["end"],
                preferred_slots=[{"day": "monday", "slots": [1, 2]}, {"day": "thursday", "slots": [1, 2]}],
                unavailable_slots=[],
                max_students=25,
                current_students=0,
                fee_amount=Decimal(cl["fee"]),
                sessions_per_week=2,
                is_online=False,
                status=cl["status"],
                notes=f"Lớp học {cl['name']} chất lượng cao."
            )
            db.add(clazz)
            db.flush()
            classes_map[cl["name"]] = clazz

        # 7. Create Enrollments
        print("Seeding Class Enrollments...")
        # Enroll students to classes
        # IELTS-FD-01: student.minh, student.khoi, student.an, student.binh, student.cuong, student.dung, student.huong, student.lan (8 students)
        # IELTS-IT-01: student.minh, student.khoi, student.an, student.nam, student.vy (5 students)
        # GE-A2-01: student.binh, student.cuong, student.dung, student.huong, student.lan, student.nam, student.vy (7 students)
        enrollments = [
            ("IELTS-FD-01", "student.minh@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("IELTS-FD-01", "student.khoi@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("IELTS-FD-01", "student.an@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("IELTS-FD-01", "student.binh@gmail.com", PaymentStatus.PENDING, EnrollmentStatus.ACTIVE),
            ("IELTS-FD-01", "student.cuong@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("IELTS-FD-01", "student.dung@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("IELTS-FD-01", "student.huong@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("IELTS-FD-01", "student.lan@gmail.com", PaymentStatus.PENDING, EnrollmentStatus.ACTIVE),
            
            ("IELTS-IT-01", "student.minh@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("IELTS-IT-01", "student.khoi@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("IELTS-IT-01", "student.an@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("IELTS-IT-01", "student.nam@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("IELTS-IT-01", "student.vy@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            
            ("GE-A2-01", "student.binh@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("GE-A2-01", "student.cuong@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("GE-A2-01", "student.dung@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("GE-A2-01", "student.huong@gmail.com", PaymentStatus.PENDING, EnrollmentStatus.ACTIVE),
            ("GE-A2-01", "student.lan@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("GE-A2-01", "student.nam@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE),
            ("GE-A2-01", "student.vy@gmail.com", PaymentStatus.PAID, EnrollmentStatus.ACTIVE)
        ]
        
        for class_name, student_email, pay_status, enroll_status in enrollments:
            clazz = classes_map[class_name]
            stud = users_map[student_email]
            enroll = ClassEnrollment(
                class_id=clazz.id,
                student_id=stud.id,
                enrollment_date=datetime.now(timezone.utc) - timedelta(days=30),
                fee_paid=clazz.fee_amount if pay_status == PaymentStatus.PAID else Decimal(0),
                payment_status=pay_status,
                status=enroll_status,
                attendance_rate=Decimal(90.0) if enroll_status == EnrollmentStatus.ACTIVE else Decimal(0),
                notes="Đăng ký tự động qua hệ thống"
            )
            db.add(enroll)
            clazz.current_students += 1
            db.flush()

        # 8. Create Class Sessions & Attendance records for active classes
        print("Seeding Class Sessions & Attendance...")
        # We create 8 sessions for IELTS-FD-01 spanning May 2026.
        # Students: student.minh, student.khoi, student.an, student.binh, student.cuong, student.dung, student.huong, student.lan
        students_fd = [users_map[e] for e in [
            "student.minh@gmail.com", "student.khoi@gmail.com", "student.an@gmail.com",
            "student.binh@gmail.com", "student.cuong@gmail.com", "student.dung@gmail.com",
            "student.huong@gmail.com", "student.lan@gmail.com"
        ]]
        
        start_date = date(2026, 5, 4) # A Monday
        teacher_fd = users_map["teacher.an@tungtung.edu.vn"]
        room_fd = rooms_map["Room 101"]
        class_fd = classes_map["IELTS-FD-01"]
        
        for i in range(8):
            session_date = start_date + timedelta(weeks=i // 2, days=0 if i % 2 == 0 else 3) # Monday or Thursday
            session = ClassSession(
                class_id=class_fd.id,
                room_id=room_fd.id,
                teacher_id=teacher_fd.id,
                session_date=session_date,
                start_time=datetime.strptime("08:00", "%H:%M").time(),
                end_time=datetime.strptime("10:00", "%H:%M").time(),
                time_slots=[1, 2],
                topic=f"IELTS Topic {i+1}: Skills development",
                description=f"Mô tả chi tiết buổi học số {i+1}",
                status=SessionStatus.COMPLETED,
                attendance_taken=True,
                notes="Buổi học hoàn thành tốt"
            )
            db.add(session)
            db.flush()
            
            # Seed attendance records for this session
            for std in students_fd:
                # Randomize slightly (mostly present, some late, some absent)
                status_choice = AttendanceStatus.PRESENT
                late_mins = 0
                if std.email == "student.an@gmail.com" and i == 2:
                    status_choice = AttendanceStatus.ABSENT
                elif std.email == "student.binh@gmail.com" and i == 4:
                    status_choice = AttendanceStatus.LATE
                    late_mins = 15
                
                att = AttendanceRecord(
                    session_id=session.id,
                    student_id=std.id,
                    marked_by=teacher_fd.id,
                    status=status_choice,
                    check_in_time=datetime.now(timezone.utc) if status_choice != AttendanceStatus.ABSENT else None,
                    late_minutes=late_mins,
                    notes="Điểm danh đầu giờ"
                )
                db.add(att)
            db.flush()

        # 9. Create Tests & Questions
        print("Seeding Tests, Questions & Test Attempts...")
        # Create a test for IELTS-FD-01
        test_fd = Test(
            title="IELTS Academic Reading Placement",
            description="Bài thi kiểm tra Reading đầu khóa để khảo sát trình độ học sinh",
            instructions="Đọc kỹ đoạn văn và trả lời 10 câu hỏi trắc nghiệm.",
            total_points=Decimal(10.0),
            time_limit_minutes=15,
            passing_score=Decimal(5.0),
            max_attempts=2,
            status=TestStatus.PUBLISHED,
            created_by=users_map["admin@tungtung.edu.vn"].id,
            course_id=courses_map["IELTS Foundation"].id,
            class_id=class_fd.id,
            test_type=TestType.MIDTERM
        )
        db.add(test_fd)
        db.flush()

        # Question Bank & Test Questions
        q_bank = []
        for q_idx in range(5):
            q = QuestionBank(
                title=f"Reading Question {q_idx+1}",
                question_text=f"Đâu là câu trả lời đúng cho đoạn văn số {q_idx+1}?",
                question_type=QuestionType.MULTIPLE_CHOICE,
                skill_area=SkillArea.READING,
                difficulty_level=DifficultyLevel.MEDIUM,
                options={"A": "Đáp án đúng", "B": "Đáp án sai 1", "C": "Đáp án sai 2", "D": "Đáp án sai 3"},
                correct_answer="A",
                points=Decimal(2.0),
                status=ContentStatus.ACTIVE
            )
            db.add(q)
            db.flush()
            q_bank.append(q)

        # Question Group
        sec = TestSection(
            test_id=test_fd.id,
            name="Section 1",
            skill_area=SkillArea.READING,
            order_number=1,
            time_limit_minutes=15
        )
        db.add(sec)
        db.flush()

        part = TestSectionPart(
            test_section_id=sec.id,
            name="Part 1",
            order_number=1
        )
        db.add(part)
        db.flush()

        group = QuestionGroup(
            part_id=part.id,
            name="Group 1",
            order_number=1,
            question_type=QuestionType.MULTIPLE_CHOICE
        )
        db.add(group)
        db.flush()

        for idx, q in enumerate(q_bank):
            t_q = TestQuestion(
                test_id=test_fd.id,
                question_id=q.id,
                group_id=group.id,
                order_number=idx+1,
                group_order_number=idx+1,
                points=Decimal(2.0)
            )
            db.add(t_q)
        db.flush()

        # 10. Test Attempts for Students
        # Let's seed attempts with different scores for each student in the class to show a beautiful chart!
        student_scores = {
            "student.minh@gmail.com": (8.0, 4, True),
            "student.khoi@gmail.com": (10.0, 5, True),
            "student.an@gmail.com": (6.0, 3, True),
            "student.binh@gmail.com": (4.0, 2, False),
            "student.cuong@gmail.com": (8.0, 4, True),
            "student.dung@gmail.com": (6.0, 3, True),
            "student.huong@gmail.com": (2.0, 1, False),
            "student.lan@gmail.com": (8.0, 4, True)
        }
        
        for email, (score, correct_count, passed) in student_scores.items():
            std = users_map[email]
            attempt = TestAttempt(
                test_id=test_fd.id,
                student_id=std.id,
                attempt_number=1,
                started_at=datetime.now(timezone.utc) - timedelta(days=5, minutes=10),
                submitted_at=datetime.now(timezone.utc) - timedelta(days=5),
                time_taken_seconds=600,
                total_score=Decimal(score),
                percentage_score=Decimal(score * 10),
                passed=passed,
                status=AttemptStatus.GRADED,
                graded_by=teacher_fd.id,
                graded_at=datetime.now(timezone.utc) - timedelta(days=5)
            )
            db.add(attempt)
        db.flush()

        # 11. KPI and Payroll Seeding
        print("Seeding KPI & Payroll module...")
        
        # Templates
        # Template for GV (Full Time)
        kpi_temp_gv = KPITemplate(
            name="KPI cho Giáo viên (GV) - Lotus Standard",
            contract_type=ContractType.FULL_TIME,
            max_bonus_amount=Decimal(15000000),
            bonus_type=BonusType.FIXED_PER_PERIOD,
            version=1,
            is_active=True,
            description="KPI chính thức áp dụng cho giáo viên cơ hữu từ kỳ 2026"
        )
        db.add(kpi_temp_gv)
        db.flush()

        # Add metric specs for KPI Template GV
        metrics_gv = [
            {"code": "A1", "name": "Tỷ lệ HS đạt điểm trung bình trở lên", "unit": MetricUnit.PERCENT, "weight": 0.4},
            {"code": "A2", "name": "Tỷ lệ HS đạt điểm cao trở lên", "unit": MetricUnit.PERCENT, "weight": 0.2},
            {"code": "B1", "name": "Tỷ lệ lên lớp đúng giờ", "unit": MetricUnit.PERCENT, "weight": 0.2},
            {"code": "C1", "name": "Tỷ lệ tiếp tục học (retention rate)", "unit": MetricUnit.PERCENT, "weight": 0.2}
        ]
        metrics_gv_map = {}
        for idx, m in enumerate(metrics_gv):
            met = KPITemplateMetric(
                template_id=kpi_temp_gv.id,
                metric_code=m["code"],
                metric_name=m["name"],
                is_group_header=False,
                unit=m["unit"],
                target_min=Decimal(0.0),
                target_max=Decimal(1.0),
                weight=Decimal(m["weight"]),
                sort_order=idx
            )
            db.add(met)
            db.flush()
            metrics_gv_map[m["code"]] = met

        # KPI Period
        kpi_period = KPIPeriod(
            name="Kỳ tháng 05/2026",
            period_type=PeriodType.MONTHLY,
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
            is_active=True
        )
        db.add(kpi_period)
        db.flush()

        # Teacher Payroll Configs for seeded teachers
        # teacher.an (Full Time), teacher.binh (Part Time)
        payroll_config_an = TeacherPayrollConfig(
            teacher_id=users_map["teacher.an@tungtung.edu.vn"].id,
            contract_type=ContractType.FULL_TIME,
            base_salary=Decimal(12000000),
            lesson_rate=Decimal(250000),
            max_kpi_bonus=Decimal(15000000),
            fixed_allowance=Decimal(1500000)
        )
        payroll_config_binh = TeacherPayrollConfig(
            teacher_id=users_map["teacher.binh@tungtung.edu.vn"].id,
            contract_type=ContractType.PART_TIME,
            base_salary=Decimal(0),
            lesson_rate=Decimal(300000),
            max_kpi_bonus=Decimal(5000000),
            fixed_allowance=Decimal(500000)
        )
        db.add(payroll_config_an)
        db.add(payroll_config_binh)
        db.flush()

        # KPI Record for teacher.an
        kpi_rec_an = KPIRecord(
            staff_id=users_map["teacher.an@tungtung.edu.vn"].id,
            period_id=kpi_period.id,
            template_id=kpi_temp_gv.id,
            total_score=Decimal(0.85),
            bonus_amount=Decimal(12750000), # 85% of 15,000,000
            teaching_hours=Decimal(40.0),
            approval_status=ApprovalStatus.APPROVED,
            submitted_at=datetime.now(timezone.utc) - timedelta(days=2),
            approved_by=users_map["admin@tungtung.edu.vn"].id,
            approved_at=datetime.now(timezone.utc) - timedelta(days=1)
        )
        db.add(kpi_rec_an)
        db.flush()

        # KPI Metric Results for teacher.an
        metric_values = {"A1": 0.90, "A2": 0.80, "B1": 0.95, "C1": 0.75}
        for code, val in metric_values.items():
            res = KPIMetricResult(
                kpi_record_id=kpi_rec_an.id,
                metric_id=metrics_gv_map[code].id,
                actual_value=Decimal(val),
                converted_score=Decimal(val),
                data_source=DataSource.AUTO_SYNC,
                note=f"Đồng bộ tự động từ hệ thống lớp học cho mã chỉ tiêu {code}"
            )
            db.add(res)
        db.flush()

        # Salary for teacher.an in monthly period
        sal_an = Salary(
            teacher_id=users_map["teacher.an@tungtung.edu.vn"].id,
            period="2026-05",
            contract_type=ContractType.FULL_TIME,
            lesson_count=20,
            base_salary_calc=Decimal(12000000),
            kpi_bonus_calc=Decimal(12750000),
            fixed_allowance=Decimal(1500000),
            total_adjustments=Decimal(500000), # Plus 500k bonus
            net_salary=Decimal(26750000), # 12M + 12.75M + 1.5M + 0.5M
            status=SalaryStatus.APPROVED,
            approved_by=users_map["admin@tungtung.edu.vn"].id,
            approved_at=datetime.now(timezone.utc)
        )
        db.add(sal_an)
        db.flush()

        # Add Salary Adjustment
        adj = SalaryAdjustment(
            salary_id=sal_an.id,
            adjustment_type=AdjustmentType.ALLOWANCE,
            amount=Decimal(500000),
            reason="Thành tích xuất sắc trong hỗ trợ học sinh yếu kém",
            created_by=users_map["admin@tungtung.edu.vn"].id
        )
        db.add(adj)
        db.flush()

        db.commit()
        print("\n[SUCCESS] Seeded all realistic Vietnamese data successfully!")
        print("Summary of data seeded:")
        print(f" - Users: {len(users_data)} users")
        print(f" - Rooms: {len(rooms_data)} rooms")
        print(f" - Courses: {len(courses_data)} courses")
        print(f" - Classes: {len(classes_data)} classes")
        print(f" - Enrollments: {len(enrollments)} enrollments")
        print(f" - Completed sessions: 8 sessions with attendance records")
        print(f" - Placement tests: 1 test with 5 questions")
        print(f" - Student test attempts: 8 graded test attempts")
        print(f" - KPI: 1 template, 4 KPI metric results, 1 monthly period, 1 KPI record approved")
        print(f" - Salary: 1 teacher salary calculated & approved (Net: 26,750,000 VND)")
        
    except Exception as e:
        db.rollback()
        print(f"[ERR] Seeding failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
