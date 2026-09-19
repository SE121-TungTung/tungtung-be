import asyncio
import uuid
from app.core.database import SessionLocal
from app.services.user_service import user_service
from app.models.user import UserRole, User
from app.core.security import get_password_hash

async def seed_users():
    db = SessionLocal()
    
    roles_to_seed = [
        {"email": "system_admin@test.com", "role": UserRole.SYSTEM_ADMIN, "first_name": "System", "last_name": "Admin"},
        {"email": "center_admin@test.com", "role": UserRole.CENTER_ADMIN, "first_name": "Center", "last_name": "Admin"},
        {"email": "office_admin@test.com", "role": UserRole.OFFICE_ADMIN, "first_name": "Office", "last_name": "Admin"},
        {"email": "teacher@test.com", "role": UserRole.TEACHER, "first_name": "Test", "last_name": "Teacher"},
        {"email": "student@test.com", "role": UserRole.STUDENT, "first_name": "Test", "last_name": "Student"},
        {"email": "guest@test.com", "role": UserRole.GUEST, "first_name": "Test", "last_name": "Guest"},
    ]
    
    default_password = "Password@123"
    hashed_pwd = get_password_hash(default_password)
    
    for user_data in roles_to_seed:
        email = user_data["email"]
        existing_user = await user_service.get_user_by_email(db, email)
        
        if not existing_user:
            print(f"Creating {email} with role {user_data['role'].value}...")
            new_user = User(
                id=uuid.uuid4(),
                email=email,
                password_hash=hashed_pwd,
                first_name=user_data["first_name"],
                last_name=user_data["last_name"],
                role=user_data["role"],
                status="active"
            )
            db.add(new_user)
        else:
            print(f"User {email} already exists. Resetting password...")
            existing_user.password_hash = hashed_pwd
            
    db.commit()
    print("Seed process completed.")
    db.close()

if __name__ == "__main__":
    asyncio.run(seed_users())
