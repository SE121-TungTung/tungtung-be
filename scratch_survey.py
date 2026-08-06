import sys
import os
from sqlalchemy import func
from sqlalchemy.orm import Session

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import SessionLocal
from app.models import User, Class, Course, ClassEnrollment, Test, TestAttempt, Room, AttendanceRecord, KPIRecord, Salary

def survey():
    db = SessionLocal()
    try:
        print("--- DATABASE SURVEY RESULTS ---")
        
        # 1. Users count by role
        print("\n[USERS BY ROLE]")
        roles = db.query(User.role, func.count(User.id)).group_by(User.role).all()
        for role, count in roles:
            print(f" - {role or 'None'}: {count}")
            
        # 2. Key entities counts
        print("\n[ENTITY COUNTS]")
        entities = {
            "Courses": Course,
            "Classes": Class,
            "Enrollments": ClassEnrollment,
            "Tests": Test,
            "Test Attempts": TestAttempt,
            "Rooms": Room,
            "Attendance Records": AttendanceRecord,
            "KPI Records": KPIRecord,
            "Salaries": Salary
        }
        for name, model in entities.items():
            count = db.query(model).count()
            print(f" - {name}: {count}")
            
        # 3. Sample Users
        print("\n[SAMPLE USERS (Top 10)]")
        users = db.query(User).limit(10).all()
        for u in users:
            print(f" - ID: {u.id} | Email: {u.email} | Name: {u.first_name} {u.last_name} | Role: {u.role}")

        # 4. Sample Classes
        print("\n[SAMPLE CLASSES (Top 5)]")
        classes = db.query(Class).limit(5).all()
        for c in classes:
            print(f" - ID: {c.id} | Name: {c.name} | Status: {c.status} | Start: {c.start_date}")
            
        # 5. Sample Tests
        print("\n[SAMPLE TESTS (Top 5)]")
        tests = db.query(Test).limit(5).all()
        for t in tests:
            print(f" - ID: {t.id} | Title: {t.title} | Type: {t.test_type}")
            
        # 6. Sample Test Attempts
        print("\n[SAMPLE TEST ATTEMPTS (Top 5)]")
        attempts = db.query(TestAttempt).limit(5).all()
        for a in attempts:
            print(f" - ID: {a.id} | Test ID: {a.test_id} | Student ID: {a.student_id} | Score: {a.total_score} | Status: {a.status}")

    except Exception as e:
        print(f"Error during database survey: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    survey()
