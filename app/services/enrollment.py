from sqlalchemy.orm import Session
from app.routers.generic_crud import CRUDBase
from app.models.academic import ClassEnrollment
from app.schemas.enrollment import ClassEnrollmentCreateAuto
from uuid import UUID

class ClassEnrollmentService:
    """Service layer chuyên xử lý logic Enrollment"""
    
    def __init__(self, repository: CRUDBase):
        self.repository = repository

    def create_auto_for_new_student(
        self, 
        db: Session, 
        student_id: UUID, 
        default_class_id: UUID
    ) -> ClassEnrollment:
        """
        Tạo bản ghi ClassEnrollment tự động cho sinh viên mới.
        """
        enrollment_in = ClassEnrollmentCreateAuto(
            student_id=student_id,
            class_id=default_class_id
        )
        
        new_enrollment = self.repository.create(
            db=db, 
            obj_in=enrollment_in.model_dump() 
        )
        
        return new_enrollment

class_enrollment_service = ClassEnrollmentService(CRUDBase(ClassEnrollment))