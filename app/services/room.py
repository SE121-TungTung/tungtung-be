from app.repositories.room import room_repository
from sqlalchemy.orm import Session
from typing import List
from app.models.academic import Room

class RoomService:
    def __init__(self):
        self.repository = room_repository
    
    async def get_available_rooms(self, db: Session, min_capacity: int = None) -> List[Room]:
        return self.repository.get_available_rooms(db, min_capacity)

room_service = RoomService()