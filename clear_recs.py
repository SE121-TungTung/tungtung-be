from app.core.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
db.execute(text("DELETE FROM recommendation_logs WHERE student_id = (SELECT id FROM users WHERE email = 'usr@example.com')"))
db.commit()
print("Cleared recommendation logs for usr@example.com successfully.")
