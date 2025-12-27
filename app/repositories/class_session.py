from app.models.academic import Room
from sqlalchemy.orm import Session
from typing import List
from app.routers.generic_crud import CRUDBase
from app.models.academic import Class
from app.models.session_attendance import ClassSession
from sqlalchemy.orm import joinedload
from uuid import UUID

class ClassRepository(CRUDBase):
    def __init__(self):
        super().__init__(Class)
    
    def get_classes_by_teacher(self, db: Session, teacher_id: UUID) -> List[Class]:
        """Lấy danh sách lớp học theo ID giáo viên"""
        return (
            db.query(Class)
            .options(
                joinedload(Class.course),
                joinedload(Class.teacher),
                joinedload(Class.substitute_teacher),
                joinedload(Class.room),
            )
            .filter(Class.teacher_id == teacher_id)
            .filter(Class.deleted_at.is_(None)) # Chỉ lấy lớp chưa bị xóa mềm
            .all()
        )
    
class ClassSessionRepository(CRUDBase):
    def __init__(self):
        super().__init__(ClassSession)

class_session_repository = ClassSessionRepository()
class_repository = ClassRepository()