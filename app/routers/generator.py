from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, create_model
import inflect
from app.schemas.generator import generate_model_schemas
from app.routers.generic_crud import CRUDBase

# Initialize inflect for proper pluralization
inflector = inflect.engine()

class RouteGenerator:
    def __init__(
        self, 
        model, 
        crud_class: CRUDBase,
        db_dependency,
        auth_dependency = None,
        tag_prefix: str = None
    ):
        self.model = model
        self.crud = crud_class
        self.get_db = db_dependency
        self.auth_dependency = auth_dependency
        
        self.model_name = model.__name__.lower()
        self.model_plural = inflector.plural(self.model_name)
        self.tag_name = tag_prefix or self.model_plural.title()
        
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
            prefix=f"/{self.model_plural}",
            tags=[self.tag_name]
        )
        
        # Conditional dependencies
        auth_dep = [Depends(self.auth_dependency)] if self.auth_dependency else []
        
        # LIST endpoint
        if 'list' in active_routes:
            @router.get(
                "/",
                response_model=Dict[str, Any],  # Paginated response
                summary=f"List {self.model_plural}",
                description=f"Retrieve a paginated list of {self.model_plural} with filtering and search"
            )
            async def list_items(
                skip: int = Query(0, ge=0, description="Number of records to skip"),
                limit: int = Query(100, ge=1, le=1000, description="Max records to return"),
                sort_by: Optional[str] = Query(None, description="Field to sort by"),
                sort_order: str = Query("asc", regex="^(asc|desc)$", description="Sort order"),
                search: Optional[str] = Query(None, description="Search term"),
                db: Session = Depends(self.get_db),
                *auth_dep
            ):
                result = self.crud.get_multi(
                    db,
                    skip=skip,
                    limit=limit,
                    search=search,
                    sort_by=sort_by,
                    sort_order=sort_order
                )
                return result
        
        # GET single item
        if 'get' in active_routes:
            @router.get(
                "/{item_id}",
                response_model=self.schemas['response'],
                summary=f"Get {self.model_name}",
                description=f"Retrieve a single {self.model_name} by ID"
            )
            async def get_item(
                item_id: str = Path(..., description=f"{self.model_name.title()} ID"),
                db: Session = Depends(self.get_db),
                *auth_dep
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
                response_model=self.schemas['response'],
                status_code=status.HTTP_201_CREATED,
                summary=f"Create {self.model_name}",
                description=f"Create a new {self.model_name}"
            )
            async def create_item(
                item: Any = self.schemas['create'],
                db: Session = Depends(self.get_db),
                *auth_dep
            ):
                return self.crud.create(db=db, obj_in=item)
        
        # UPDATE endpoint
        if 'update' in active_routes:
            @router.put(
                "/{item_id}",
                response_model=self.schemas['response'],
                summary=f"Update {self.model_name}",
                description=f"Update an existing {self.model_name}"
            )
            async def update_item(
                item_id: str = Path(..., description=f"{self.model_name.title()} ID"),
                item: Any = self.schemas['update'],
                db: Session = Depends(self.get_db),
                *auth_dep
            ):
                db_item = self.crud.get(db, id=item_id)
                if db_item is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"{self.model_name.title()} not found"
                    )
                return self.crud.update(db=db, db_obj=db_item, obj_in=item)
        
        # DELETE endpoint
        if 'delete' in active_routes:
            @router.delete(
                "/{item_id}",
                summary=f"Delete {self.model_name}",
                description=f"Delete a {self.model_name}"
            )
            async def delete_item(
                item_id: str = Path(..., description=f"{self.model_name.title()} ID"),
                soft: bool = Query(False, description="Perform soft delete if supported"),
                db: Session = Depends(self.get_db),
                *auth_dep
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
    exclude_routes: List[str] = None
) -> APIRouter:
    """Helper function to quickly create a CRUD router for a model"""
    
    # Create CRUD class instance
    crud = CRUDBase(model)
    
    # Create route generator
    generator = RouteGenerator(
        model=model,
        crud_class=crud,
        db_dependency=db_dependency,
        auth_dependency=auth_dependency
    )
    
    # Generate and return router
    return generator.generate_router(
        include_routes=include_routes,
        exclude_routes=exclude_routes
    )