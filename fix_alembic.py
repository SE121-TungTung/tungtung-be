from app.core.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("UPDATE alembic_version SET version_num = 'f2b3c4d5e6f7'"))
db.commit()
print("updated")
