import math

from app.models.academic import Room
from sqlalchemy.orm import Session
from typing import List
from app.routers.generic_crud import CRUDBase
from app.models.academic import Class
from app.models.session_attendance import ClassSession
from sqlalchemy.orm import joinedload
from uuid import UUID

from app.schemas.base_schema import PaginationMetadata, PaginationResponse
from app.schemas.classes import ClassResponse

class ClassRepository(CRUDBase):
    def __init__(self):
        super().__init__(Class)
    
def get_classes_by_teacher(
        self, 
        db: Session, 
        teacher_id: UUID, 
        page: int = 1, 
        limit: int = 20
    ) -> PaginationResponse[ClassResponse]:
        """Lấy danh sách lớp học theo ID giáo viên có phân trang"""
        
        # 1. Tính toán skip ngay trong Service
        skip = (page - 1) * limit

        # 2. Khởi tạo Base Query để đếm (Chưa cần joinedload để count cho nhẹ)
        base_query = (
            db.query(Class)
            .filter(Class.teacher_id == teacher_id)
            .filter(Class.deleted_at.is_(None)) # Chỉ lấy lớp chưa bị xóa mềm
        )

        # 3. Đếm tổng & Tạo Metadata
        total = base_query.count()
        total_pages = math.ceil(total / limit) if limit > 0 else 1

        meta = PaginationMetadata(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages
        )

        # 4. Truy vấn lấy dữ liệu thật (Gắn joinedload, phân trang và sắp xếp)
        classes = (
            base_query
            .options(
                joinedload(Class.course),
                joinedload(Class.teacher),
                joinedload(Class.substitute_teacher),
                joinedload(Class.room),
            )
            .order_by(Class.created_at.desc()) # LƯU Ý: Rất nên thêm order_by để danh sách ổn định khi phân trang
            .offset(skip)
            .limit(limit)
            .all()
        )

        # 5. Explicit Mapping: Ép kiểu tường minh từng ORM Object sang Pydantic Model
        results = [ClassResponse.model_validate(c) for c in classes]

        # 6. Trả về chuẩn format
        return PaginationResponse(
            data=results,
            meta=meta
        )
    
class ClassSessionRepository(CRUDBase):
    def __init__(self):
        super().__init__(ClassSession)

class_session_repository = ClassSessionRepository()
class_repository = ClassRepository()