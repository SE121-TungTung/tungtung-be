from typing import List
from sqlalchemy.orm import Session, joinedload
from app.repositories.base import BaseRepository
from app.models.academic import Class, ClassEnrollment

class ClassRepository(BaseRepository[Class]):
    def __init__(self):
        super().__init__(Class)

    def get_active_classes_with_students(self, db: Session) -> List[Class]:
        """
        Fetch all active classes with their enrollments and students loaded eagerly.
        """
        return db.query(Class).options(
            joinedload(Class.enrollments).joinedload(ClassEnrollment.student)
        ).filter(
            Class.status == 'active',
            Class.deleted_at.is_(None)
        ).all()

class_repository = ClassRepository()
