from typing import Type, TypeVar, Generic, List, Optional, Any, Dict, Union
from sqlalchemy.orm import Session, Query
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.inspection import inspect
from sqlalchemy import desc, asc, and_, or_, func, text
from pydantic import BaseModel
from fastapi import HTTPException
import logging
import math
from sqlalchemy import String, Text

ModelType = TypeVar("ModelType", bound=DeclarativeMeta)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)

logger = logging.getLogger(__name__)

class CRUDBase(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model
        self.pk_column = self._get_primary_key()
        self.searchable_fields = self._get_searchable_fields()
        self.sortable_fields = self._get_sortable_fields()
    
    def _get_primary_key(self):
        """Get primary key column dynamically"""
        inspector = inspect(self.model)
        pk_columns = inspector.primary_key
        if not pk_columns:
            raise ValueError(f"Model {self.model.__name__} has no primary key")
        return pk_columns[0]
    
    def _get_searchable_fields(self):
        """Get text fields suitable for search"""
        mapper = inspect(self.model)
        return [
            col.name for col in mapper.columns
            if isinstance(col.type, (String, Text)) and col.name not in ['password_hash', 'token']
        ]
    
    def _get_sortable_fields(self):
        """Get fields suitable for sorting"""
        mapper = inspect(self.model)
        return [col.name for col in mapper.columns]
    
    def get(self, db: Session, id: Any) -> Optional[ModelType]:
        """Get single record by ID"""
        try:
            return db.query(self.model).filter(self.pk_column == id).first()
        except Exception as e:
            logger.error(f"Error getting {self.model.__name__} with id {id}: {e}")
            return None
    
    def get_multi(
        self, 
        db: Session, 
        *,
        skip: int = 0, 
        limit: int = 100,
        filters: Dict[str, Any] = None,
        search: str = None,
        sort_by: str = None,
        sort_order: str = "asc"
    ) -> Dict[str, Any]:
        """Get multiple records with advanced filtering and pagination"""
        try:
            query = db.query(self.model)
            
            # Apply filters
            if filters:
                query = self._apply_filters(query, filters)
            
            # Apply search
            if search and self.searchable_fields:
                search_conditions = []
                for field in self.searchable_fields:
                    column = getattr(self.model, field)
                    search_conditions.append(column.ilike(f"%{search}%"))
                
                if search_conditions:
                    query = query.filter(or_(*search_conditions))
            
            # Count total before pagination
            total = query.count()
            
            # Apply sorting
            if sort_by and sort_by in self.sortable_fields:
                column = getattr(self.model, sort_by)
                if sort_order.lower() == "desc":
                    query = query.order_by(desc(column))
                else:
                    query = query.order_by(asc(column))
            else:
                # Default sorting by primary key
                query = query.order_by(asc(self.pk_column))
            
            # Apply pagination
            items = query.offset(skip).limit(limit).all()
            
            return {
                "items": items,
                "total": total,
                "page": (skip // limit) + 1 if limit > 0 else 1,
                "size": limit,
                "pages": math.ceil(total / limit) if limit > 0 else 1,
                "has_next": skip + limit < total,
                "has_prev": skip > 0
            }
            
        except Exception as e:
            logger.error(f"Error getting {self.model.__name__} list: {e}")
            raise HTTPException(status_code=500, detail=f"Error retrieving records: {str(e)}")
    
    def _apply_filters(self, query: Query, filters: Dict[str, Any]) -> Query:
        """Apply filters to query with support for different operators"""
        for key, value in filters.items():
            if not hasattr(self.model, key) or value is None:
                continue
            
            column = getattr(self.model, key)
            
            # Handle different filter types
            if isinstance(value, dict):
                # Advanced filtering: {"gte": 10}, {"like": "test"}, {"in": [1,2,3]}
                for op, op_value in value.items():
                    if op == "gte":
                        query = query.filter(column >= op_value)
                    elif op == "lte":
                        query = query.filter(column <= op_value)
                    elif op == "gt":
                        query = query.filter(column > op_value)
                    elif op == "lt":
                        query = query.filter(column < op_value)
                    elif op == "like":
                        query = query.filter(column.ilike(f"%{op_value}%"))
                    elif op == "in":
                        query = query.filter(column.in_(op_value))
                    elif op == "not_in":
                        query = query.filter(~column.in_(op_value))
                    elif op == "ne":
                        query = query.filter(column != op_value)
            elif isinstance(value, list):
                # IN filter
                query = query.filter(column.in_(value))
            else:
                # Exact match
                query = query.filter(column == value)
        
        return query
    
    def create(self, db: Session, *, obj_in: Union[CreateSchemaType, Dict[str, Any]]) -> ModelType:
        """Create new record with enhanced error handling"""
        try:
            obj_in_data = obj_in.dict() if hasattr(obj_in, 'dict') else obj_in
            
            # Remove None values for cleaner inserts
            obj_in_data = {k: v for k, v in obj_in_data.items() if v is not None}
            
            db_obj = self.model(**obj_in_data)
            db.add(db_obj)
            db.commit()
            db.refresh(db_obj)
            return db_obj
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating {self.model.__name__}: {e}")
            raise HTTPException(status_code=400, detail=f"Error creating record: {str(e)}")
    
    def update(
        self, 
        db: Session, 
        *, 
        db_obj: ModelType, 
        obj_in: Union[UpdateSchemaType, Dict[str, Any]]
    ) -> ModelType:
        """Update record with partial update support"""
        try:
            if hasattr(obj_in, 'dict'):
                update_data = obj_in.dict(exclude_unset=True)
            else:
                update_data = obj_in
            
            # Only update fields that are provided
            for field, value in update_data.items():
                if hasattr(db_obj, field) and value is not None:
                    setattr(db_obj, field, value)
            
            db.add(db_obj)
            db.commit()
            db.refresh(db_obj)
            return db_obj
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating {self.model.__name__}: {e}")
            raise HTTPException(status_code=400, detail=f"Error updating record: {str(e)}")
    
    def delete(self, db: Session, *, id: Any) -> ModelType:
        """Delete record (hard delete)"""
        try:
            obj = self.get(db, id)
            if not obj:
                raise HTTPException(
                    status_code=404, 
                    detail=f"{self.model.__name__} not found"
                )
            
            db.delete(obj)
            db.commit()
            return obj
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting {self.model.__name__} with id {id}: {e}")
            raise HTTPException(status_code=500, detail="Error deleting record")
    
    def soft_delete(self, db: Session, *, id: Any) -> ModelType:
        """Soft delete with support for different soft delete patterns"""
        try:
            obj = self.get(db, id)
            if not obj:
                raise HTTPException(
                    status_code=404, 
                    detail=f"{self.model.__name__} not found"
                )
            
            # Try different soft delete patterns
            if hasattr(obj, 'is_active'):
                obj.is_active = False
            elif hasattr(obj, 'status'):
                obj.status = 'inactive'  # or 'deleted'
            elif hasattr(obj, 'deleted_at'):
                from datetime import datetime
                obj.deleted_at = datetime.utcnow()
            else:
                # No soft delete support, use hard delete
                return self.delete(db, id=id)
            
            db.commit()
            db.refresh(obj)
            return obj
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error soft deleting {self.model.__name__} with id {id}: {e}")
            raise HTTPException(status_code=500, detail="Error deleting record")
    
    def get_by_field(self, db: Session, field_name: str, value: Any) -> Optional[ModelType]:
        """Get record by any field"""
        if not hasattr(self.model, field_name):
            return None
        
        try:
            return db.query(self.model).filter(
                getattr(self.model, field_name) == value
            ).first()
        except Exception as e:
            logger.error(f"Error getting {self.model.__name__} by {field_name}: {e}")
            return None
    
    def exists(self, db: Session, id: Any) -> bool:
        """Check if record exists"""
        return db.query(
            db.query(self.model).filter(self.pk_column == id).exists()
        ).scalar()
    