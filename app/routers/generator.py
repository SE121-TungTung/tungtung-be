import math

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional, Type, get_type_hints
from pydantic import BaseModel, create_model, Field
import inflect
from app.schemas.generator import generate_model_schemas
from app.routers.generic_crud import CRUDBase

from app.schemas.base_schema import ApiResponse, PaginationResponse, PaginationMetadata
from app.core.route import ResponseWrapperRoute

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
        active_routes = [route for route in include_routes if route not in exclude_routes]
        
        # --- BƯỚC 1: THÊM RESPONSE WRAPPER VÀO ROUTER ---
        router = APIRouter(
            prefix=self.prefix,
            tags=[self.tag_name],
            route_class=ResponseWrapperRoute  # Tự động bọc ApiResponse
        )
        
        # Lấy các Pydantic Model Class ra khỏi dictionary
        ResponseSchema = self.schemas['response']
        CreateSchema = self.schemas['create']
        UpdateSchema = self.schemas['update']
        
        # XÓA BỎ HOÀN TOÀN: PaginatedBase và ListResponseSchema tự chế ở đây
        
        auth_dep = [Depends(self.auth_dependency)] if self.auth_dependency else []
        db_dep = Depends(self.get_db)

        # LIST endpoint
        if 'list' in active_routes:
            @router.get(
                "",
                response_model=PaginationResponse[ResponseSchema], # --- CẬP NHẬT SWAGGER ---
                summary=f"List {self.model_plural}",
                description=f"Retrieve a paginated list of {self.model_plural}",
                dependencies=auth_dep
            )
            async def list_items(
                page: int = Query(1, ge=1, description="Current page"), # Đổi skip thành page cho chuẩn UI
                limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
                sort_by: Optional[str] = Query(None, description="Field to sort by"),
                sort_order: str = Query("asc", regex="^(asc|desc)$", description="Sort order"),
                search: Optional[str] = Query(None, description="Search term"),
                include_deleted: bool = Query(False, description="Set true to include soft-deleted records"),
                db: Session = db_dep
            ):
                skip = (page - 1) * limit
                
                # CRUD trả về kiểu dict cũ {"items": [...], "total": ...}
                result = self.crud.get_multi(
                    db, skip=skip, limit=limit, search=search,
                    sort_by=sort_by, sort_order=sort_order, include_deleted=include_deleted
                )
                
                # --- FIX LỖI PYDANTIC V2: Serialize ORM sang Pydantic ---
                validated_items = [ResponseSchema.model_validate(item) for item in result["items"]]
                
                # --- CHUẨN HÓA THÀNH PaginationResponse ---
                total = result["total"]
                meta = PaginationMetadata(
                    page=page,
                    limit=limit,
                    total=total,
                    total_pages=math.ceil(total / limit) if limit > 0 else 1
                )
                return PaginationResponse(data=validated_items, meta=meta)
        
        # GET single item
        if 'get' in active_routes:
            @router.get(
                "/{id}",
                response_model=ApiResponse[ResponseSchema], # --- CẬP NHẬT SWAGGER ---
                summary=f"Get {self.model_name}",
                dependencies=auth_dep
            )
            async def get_item(
                id: str = Path(..., description=f"{self.model_name.title()} ID"),
                db: Session = db_dep
            ):
                db_item = self.crud.get(db, id=id)
                if db_item is None:
                    # Chuyển sang ném Exception chuẩn của bạn nếu muốn, hoặc giữ nguyên
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
                return db_item # Trả thẳng ORM, Wrapper sẽ bọc lại
        
        # CREATE endpoint
        if 'create' in active_routes:
            @router.post(
                "",
                response_model=ApiResponse[ResponseSchema], # --- CẬP NHẬT SWAGGER ---
                status_code=status.HTTP_201_CREATED,
                summary=f"Create {self.model_name}",
                dependencies=auth_dep
            )
            async def create_item(
                item: Any = Body(...), db: Session = db_dep
            ):
                return self.crud.create(db=db, obj_in=item)
            _update_type_hints(create_item, {"item": CreateSchema})
        
        # UPDATE endpoint
        if 'update' in active_routes:
            @router.put(
                "/{id}",
                response_model=ApiResponse[ResponseSchema], # --- CẬP NHẬT SWAGGER ---
                summary=f"Update {self.model_name}",
                dependencies=auth_dep
            )
            async def update_item(
                id: str = Path(...), item: Any = Body(...), db: Session = db_dep
            ):
                db_item = self.crud.get(db, id=id)
                if db_item is None:
                    raise HTTPException(status_code=404, detail="Not found")
                return self.crud.update(db=db, db_obj=db_item, obj_in=item)
            _update_type_hints(update_item, {"item": UpdateSchema})
        
        # DELETE endpoint
        if 'delete' in active_routes:
            @router.delete(
                "/{id}",
                response_model=ApiResponse[Dict], # --- CẬP NHẬT SWAGGER ---
                summary=f"Delete {self.model_name}",
                dependencies=auth_dep
            )
            async def delete_item(
                id: str = Path(...), soft: bool = Query(True), db: Session = db_dep
            ):
                if soft:
                    self.crud.soft_delete(db=db, id=id)
                else:
                    self.crud.delete(db=db, id=id)
                
                # --- KHÔNG DÙNG JSONResponse NỮA ---
                # Chỉ cần trả về Dict, Wrapper sẽ tự bọc thành {success: true, data: {...}}
                return {
                    "message": f"{self.model_name.title()} deleted successfully",
                    "id": str(id)
                }
        
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