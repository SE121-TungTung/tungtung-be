from typing import Generic, TypeVar, Optional, List
from sqlalchemy.orm import Session
from app.repositories.base import BaseRepository

T = TypeVar("T")

class BaseService(Generic[T]):
    def __init__(self, repository: BaseRepository[T]):
        self.repository = repository
    
    async def get(self, db: Session, id: int) -> Optional[T]:
        return self.repository.get(db, id)
    
    async def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[T]:
        return self.repository.get_all(db, skip, limit)
    
    async def create(self, db: Session, obj_in: dict) -> T:
        return self.repository.create(db, obj_in)
    
    async def update(self, db: Session, db_obj: T, obj_in: dict) -> T:
        return self.repository.update(db, db_obj, obj_in)
    
    async def delete(self, db: Session, id: int) -> None:
        return self.repository.delete(db, id)
