import math

from app.repositories.room import room_repository
from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.academic import Room
from app.schemas.base_schema import PaginationMetadata, PaginationResponse
from app.schemas.room import RoomResponse

class RoomService:
    def __init__(self):
        self.repository = room_repository
    
    async def get_available_rooms(
        self, 
        db: Session, 
        min_capacity: Optional[int] = None,
        page: int = 1,      # <-- Sửa thành page
        limit: int = 20     # <-- Sửa thành limit
    ) -> PaginationResponse[RoomResponse]:
        
        # 1. Tính toán skip
        skip = (page - 1) * limit
        
        # 2. Build Base Query
        # Giả sử Room của bạn có cờ is_available hoặc status, bạn thêm filter tương ứng nhé
        query = db.query(Room).filter(Room.deleted_at.is_(None))
        
        # Ví dụ nếu bạn có cột status:
        # query = query.filter(Room.status == 'AVAILABLE')
        
        if min_capacity is not None:
            query = query.filter(Room.capacity >= min_capacity)
            
        # 3. Đếm tổng & Tạo Metadata
        total = query.count()
        total_pages = math.ceil(total / limit) if limit > 0 else 1
        
        meta = PaginationMetadata(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages
        )
        
        # 4. Lấy dữ liệu phân trang
        rooms = (
            query
            .order_by(Room.name.asc()) # Nên có order_by (ví dụ xếp theo tên phòng)
            .offset(skip)
            .limit(limit)
            .all()
        )

        results = [RoomResponse.model_validate(room) for room in rooms]

        # 6. Trả về format chuẩn
        return PaginationResponse(
            data=results,
            meta=meta
        )

room_service = RoomService()