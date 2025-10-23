from fastapi import APIRouter
from app.core.database import get_db
from app.dependencies import get_current_admin_user
from app.models.academic import Class
from app.routers.generator import create_crud_router

# Generate base CRUD
base_router = create_crud_router(
    model=Class,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user
)

# Main router
router = APIRouter(tags=["Classes"])
router.include_router(base_router, prefix="")