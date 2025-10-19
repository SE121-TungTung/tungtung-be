# TEMPORARY NOT USED
# 
# from pydantic import BaseModel, Field, validator
# from typing import Optional, List, Dict, Any
# from decimal import Decimal
# from datetime import datetime
# from app.models.academic import CourseLevel, CourseType, CourseStatus
# import uuid

# class CourseBase(BaseModel):
#     name: str = Field(..., min_length=1, max_length=255)
#     description: Optional[str] = None
#     level: CourseLevel
#     course_type: CourseType = CourseType.GENERAL_ENGLISH
#     duration_hours: int = Field(..., gt=0)
#     max_students: int = Field(25, ge=5, le=30)
#     min_students: int = Field(8, ge=3)
#     fee_amount: Decimal = Field(..., ge=0)
#     currency: str = Field("VND", max_length=3)
#     syllabus: Optional[Dict[str, Any]] = None
#     learning_objectives: Optional[List[str]] = []
#     prerequisites: Optional[List[str]] = []
#     status: CourseStatus = CourseStatus.ACTIVE
    
#     @validator('min_students')
#     def validate_min_students(cls, v, values):
#         if 'max_students' in values and v > values['max_students']:
#             raise ValueError('min_students must be <= max_students')
#         return v

# class CourseCreate(CourseBase):
#     pass

# class CourseUpdate(BaseModel):
#     name: Optional[str] = None
#     description: Optional[str] = None
#     level: Optional[CourseLevel] = None
#     course_type: Optional[CourseType] = None
#     duration_hours: Optional[int] = Field(None, gt=0)
#     max_students: Optional[int] = Field(None, ge=5, le=30)
#     min_students: Optional[int] = Field(None, ge=3)
#     fee_amount: Optional[Decimal] = Field(None, ge=0)
#     syllabus: Optional[Dict[str, Any]] = None
#     learning_objectives: Optional[List[str]] = None
#     prerequisites: Optional[List[str]] = None
#     status: Optional[CourseStatus] = None

# class CourseResponse(CourseBase):
#     id: uuid.UUID
#     created_at: datetime
#     updated_at: datetime
    
#     class Config:
#         from_attributes = True

# class CourseListResponse(BaseModel):
#     items: List[CourseResponse]
#     total: int
#     page: int
#     size: int
#     pages: int
