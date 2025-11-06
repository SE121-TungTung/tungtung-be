from typing import Generic, Type, TypeVar, List, Optional
from sqlalchemy.orm import Session

T = TypeVar("T")

class BaseRepository(Generic[T]):
    def __init__(self, model: Type[T]):
        self.model = model

    def get(self, db: Session, id: int) -> Optional[T]:
        return db.query(self.model).filter(self.model.deleted_at.is_(None)).get(id)

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[T]:
        return db.query(self.model).filter(self.model.deleted_at.is_(None)).offset(skip).limit(limit).all()

    def create(self, db: Session, obj_in: dict) -> T:
        db_obj = self.model(**obj_in)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(self, db: Session, db_obj: T, obj_in: dict) -> T:
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, id: int) -> None:
        obj = db.query(self.model).get(id)
        if obj:
            db.delete(obj)
            db.commit()
