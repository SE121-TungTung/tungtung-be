from app.routers.generic_crud import CRUDBase
from app.models.academic import Room
from sqlalchemy.orm import Session
from typing import List

class RoomRepository(CRUDBase):
    def __init__(self):
        super().__init__(Room)
    
    def get_available_rooms(self, db: Session, min_capacity: int = None) -> List[Room]:
        """Get available rooms with capacity filter"""
        query = db.query(Room).filter(Room.status == "available")
        if min_capacity:
            query = query.filter(Room.capacity >= min_capacity)
        return query.all()

room_repository = RoomRepository()