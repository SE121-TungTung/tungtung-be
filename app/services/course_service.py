import math
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional

from app.schemas.base_schema import PaginationResponse, PaginationMetadata
from app.schemas.course import CourseResponse # Giả định file schema
from app.models.academic import Course, CourseStatus

class CourseService:
    
    async def get_active_courses(
        self, db: Session, page: int = 1, limit: int = 20
    ) -> PaginationResponse[CourseResponse]:
        skip = (page - 1) * limit
        
        # Giả định Course có cờ is_active và deleted_at
        query = db.query(Course).filter(Course.deleted_at.is_(None), Course.status == CourseStatus.ACTIVE)
        
        total = query.count()
        meta = PaginationMetadata(
            page=page, limit=limit, total=total, 
            total_pages=math.ceil(total / limit) if limit > 0 else 1
        )
        
        items = query.order_by(Course.created_at.desc()).offset(skip).limit(limit).all()
        results = [CourseResponse.model_validate(item) for item in items]
        
        return PaginationResponse(data=results, meta=meta)

    async def get_by_level(
        self, db: Session, level: str, page: int = 1, limit: int = 20
    ) -> PaginationResponse[CourseResponse]:
        skip = (page - 1) * limit
        
        query = db.query(Course).filter(Course.deleted_at.is_(None), Course.level == level)
        
        total = query.count()
        meta = PaginationMetadata(
            page=page, limit=limit, total=total, 
            total_pages=math.ceil(total / limit) if limit > 0 else 1
        )
        
        items = query.order_by(Course.created_at.desc()).offset(skip).limit(limit).all()
        results = [CourseResponse.model_validate(item) for item in items]
        
        return PaginationResponse(data=results, meta=meta)

    async def search_courses(
        self, db: Session, search_query: str, page: int = 1, limit: int = 20
    ) -> PaginationResponse[CourseResponse]:
        skip = (page - 1) * limit
        query = db.query(Course).filter(Course.deleted_at.is_(None))
        
        if search_query:
            query = query.filter(
                or_(
                    Course.name.ilike(f"%{search_query}%"),
                    Course.description.ilike(f"%{search_query}%")
                )
            )
            
        total = query.count()
        meta = PaginationMetadata(
            page=page, limit=limit, total=total, 
            total_pages=math.ceil(total / limit) if limit > 0 else 1
        )
        
        items = query.order_by(Course.created_at.desc()).offset(skip).limit(limit).all()
        results = [CourseResponse.model_validate(item) for item in items]
        
        return PaginationResponse(data=results, meta=meta)

course_service = CourseService()