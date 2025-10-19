from app.repositories.course import course_repository
from sqlalchemy.orm import Session
from typing import List
from app.models.academic import Course

class CourseService:
    def __init__(self):
        self.repository = course_repository
    
    async def get_by_level(self, db: Session, level: str) -> List[Course]:
        return self.repository.get_by_level(db, level)
    
    async def get_active_courses(self, db: Session) -> List[Course]:
        return self.repository.get_active_courses(db)
    
    async def search_courses(self, db: Session, query: str) -> List[Course]:
        return self.repository.search_courses(db, query)

course_service = CourseService()