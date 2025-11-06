from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional, Type, get_type_hints
from pydantic import BaseModel, create_model, Field
import inflect
from app.schemas.generator import generate_model_schemas
from app.routers.generic_crud import CRUDBase

# Initialize inflect for proper pluralization
inflector = inflect.engine()

# Hàm helper để cập nhật type hints cho các hàm được tạo động
def _update_type_hints(func, hints: Dict[str, Type]):
    """Applies type hints dynamically to a function to resolve dynamic types."""
    existing_hints = get_type_hints(func)
    
    for name, type_ in hints.items():
        existing_hints[name] = type_
        
    func.__annotations__ = existing_hints


class RouteGenerator:
    def __init__(
        self, 
        model, 
        crud_class: CRUDBase,
        db_dependency,
        auth_dependency = None,
        prefix: str = None,
        tag_prefix: str = None
    ):
        self.model = model
        self.crud = crud_class
        self.get_db = db_dependency
        self.auth_dependency = auth_dependency
        
        self.model_name = model.__name__.lower()
        self.model_plural = inflector.plural(self.model_name)
        self.tag_name = tag_prefix or self.model_plural.title()
        self.prefix = prefix if prefix is not None else f"/{self.model_plural}"
        
        # Auto-generate schemas
        self.schemas = generate_model_schemas(model)
    
    def generate_router(
        self, 
        include_routes: List[str] = None,
        exclude_routes: List[str] = None
    ) -> APIRouter:
        """Generate router with configurable routes"""
        
        include_routes = include_routes or ['list', 'get', 'create', 'update', 'delete']
        exclude_routes = exclude_routes or []
        
        # Filter routes
        active_routes = [route for route in include_routes if route not in exclude_routes]
        
        router = APIRouter(
            prefix=self.prefix,
            tags=[self.tag_name]
        )
        
        # Lấy các Pydantic Model Class ra khỏi dictionary
        ResponseSchema = self.schemas['response']
        CreateSchema = self.schemas['create']
        UpdateSchema = self.schemas['update']
        
        # --- FIX LỖI PydanticUserError BẰNG CÁCH DÙNG MODEL BASE ---
        
        # 1. Định nghĩa Base Model cho Phân trang (chứa model_config)
        class PaginatedBase(BaseModel):
            """Base model for paginated responses, defining common fields and config."""
            # Cài đặt model_config (from_attributes=True) là thuộc tính của Class
            model_config = {'from_attributes': True}
            
            # Định nghĩa các trường phân trang (chúng ta có thể ghi đè chúng trong create_model)
            total: int = 0
            page: int = 1
            size: int = 100
            pages: int = 1
            has_next: bool = False
            has_prev: bool = False
        
        # 2. Tạo ListResponseSchema bằng cách thừa kế từ PaginatedBase
        ListResponseSchema = create_model(
            f"{self.model_name.title()}ListResponse",
            # Sử dụng __base__ để thừa kế các trường và model_config
            __base__=PaginatedBase, 
            # Định nghĩa trường 'items' (Trường mới duy nhất)
            items=(List[ResponseSchema], Field(..., description=f"List of {self.model_plural}")),
            # KHÔNG cần truyền model_config ở đây
        )
        # -------------------------------------------------------
        
        # Conditional dependencies
        auth_dep = [Depends(self.auth_dependency)] if self.auth_dependency else []
        db_dep = Depends(self.get_db)

        # LIST endpoint
        if 'list' in active_routes:
            @router.get(
                "/",
                response_model=ListResponseSchema,  # FIX LỖI Serialization
                summary=f"List {self.model_plural}",
                description=f"Retrieve a paginated list of {self.model_plural} with filtering and search",
                dependencies=auth_dep
            )
            async def list_items(
                skip: int = Query(0, ge=0, description="Number of records to skip"),
                limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
                sort_by: Optional[str] = Query(None, description="Field to sort by"),
                sort_order: str = Query("asc", regex="^(asc|desc)$", description="Sort order"),
                search: Optional[str] = Query(None, description="Search term"),
                include_deleted: bool = Query(False, description="Set true to include soft-deleted records"),
                db: Session = db_dep
            ):
                result = self.crud.get_multi(
                    db,
                    skip=skip,
                    limit=limit,
                    search=search,
                    sort_by=sort_by,
                    sort_order=sort_order,
                    include_deleted=include_deleted
                )
                return result
        
        # GET single item
        if 'get' in active_routes:
            @router.get(
                "/{item_id}",
                response_model=ResponseSchema,
                summary=f"Get {self.model_name}",
                description=f"Retrieve a single {self.model_name} by ID",
                dependencies=auth_dep
            )
            async def get_item(
                item_id: str = Path(..., description=f"{self.model_name.title()} ID"),
                db: Session = db_dep
            ):
                db_item = self.crud.get(db, id=item_id)
                if db_item is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"{self.model_name.title()} not found"
                    )
                return db_item
        
        # CREATE endpoint
        if 'create' in active_routes:
            @router.post(
                "/",
                response_model=ResponseSchema,
                status_code=status.HTTP_201_CREATED,
                summary=f"Create {self.model_name}",
                description=f"Create a new {self.model_name}",
                dependencies=auth_dep
            )
            async def create_item(
                # FIX LỖI CÚ PHÁP: Dùng Any làm placeholder.
                item: Any = Body(..., description=f"The {self.model_name} data to create"), 
                db: Session = db_dep
            ):
                return self.crud.create(db=db, obj_in=item)
            
            # Gán kiểu dữ liệu động sau khi hàm được định nghĩa
            _update_type_hints(create_item, {"item": CreateSchema})
        
        # UPDATE endpoint
        if 'update' in active_routes:
            @router.put(
                "/{item_id}",
                response_model=ResponseSchema,
                summary=f"Update {self.model_name}",
                description=f"Update an existing {self.model_name}",
                dependencies=auth_dep
            )
            async def update_item(
                item_id: str = Path(..., description=f"{self.model_name.title()} ID"),
                # FIX LỖI CÚ PHÁP: Dùng Any làm placeholder.
                item: Any = Body(..., description=f"The {self.model_name} data to update"),
                db: Session = db_dep
            ):
                db_item = self.crud.get(db, id=item_id)
                if db_item is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"{self.model_name.title()} not found"
                    )
                return self.crud.update(db=db, db_obj=db_item, obj_in=item)
            
            # Gán kiểu dữ liệu động sau khi hàm được định nghĩa
            _update_type_hints(update_item, {"item": UpdateSchema})
        
        # DELETE endpoint
        if 'delete' in active_routes:
            @router.delete(
                "/{item_id}",
                summary=f"Delete {self.model_name}",
                description=f"Delete a {self.model_name}",
                dependencies=auth_dep
            )
            async def delete_item(
                item_id: str = Path(..., description=f"{self.model_name.title()} ID"),
                soft: bool = Query(True, description="Perform soft delete if supported"),
                db: Session = db_dep
            ):
                if soft:
                    deleted_item = self.crud.soft_delete(db=db, id=item_id)
                else:
                    deleted_item = self.crud.delete(db=db, id=item_id)
                
                return JSONResponse(
                    content={
                        "message": f"{self.model_name.title()} deleted successfully",
                        "id": str(item_id)
                    },
                    status_code=status.HTTP_200_OK
                )
        
        return router

# Usage helper function
def create_crud_router(
    model,
    db_dependency,
    auth_dependency = None,
    include_routes: List[str] = None,
    exclude_routes: List[str] = None,
    prefix: str = None,
    tag_prefix: str = None
) -> APIRouter:
    """Helper function to quickly create a CRUD router for a model"""
    
    # Create CRUD class instance
    crud = CRUDBase(model)
    
    # Create route generator
    generator = RouteGenerator(
        model=model,
        crud_class=crud,
        db_dependency=db_dependency,
        auth_dependency=auth_dependency,
        prefix=prefix,
        tag_prefix=tag_prefix
    )
    
    # Generate and return router
    return generator.generate_router(
        include_routes=include_routes,
        exclude_routes=exclude_routes
    )