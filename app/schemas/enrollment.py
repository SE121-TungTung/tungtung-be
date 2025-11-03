from pydantic import BaseModel
from uuid import UUID

class ClassEnrollmentCreateAuto(BaseModel):
    student_id: UUID
    class_id: UUID
