from app.routers.generic_crud import CRUDBase
from app.models.academic import Course
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List

class CourseRepository(CRUDBase):
    def __init__(self):
        super().__init__(Course)
    
    def get_by_level(self, db: Session, level: str) -> List[Course]:
        """Get active courses by level"""
        return db.query(Course).filter(
            Course.level == level,
            Course.status == "active"
        ).all()
    
    def get_active_courses(self, db: Session) -> List[Course]:
        """Get all active courses"""
        return db.query(Course).filter(Course.status == "active").all()
    
    def search_courses(self, db: Session, query: str) -> List[Course]:
        """Search in name and description"""
        search_filter = or_(
            Course.name.ilike(f"%{query}%"),
            Course.description.ilike(f"%{query}%")
        )
        return db.query(Course).filter(search_filter).all()

course_repository = CourseRepository()