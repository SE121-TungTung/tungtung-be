from app.models.academic import Room
from sqlalchemy.orm import Session
from typing import List
from app.routers.generic_crud import CRUDBase
from app.models.academic import Class
from app.models.session_attendance import ClassSession

class ClassRepository(CRUDBase):
    def __init__(self):
        super().__init__(Class)
    
class ClassSessionRepository(CRUDBase):
    def __init__(self):
        super().__init__(ClassSession)

class_session_repository = ClassSessionRepository()
class_repository = ClassRepository()