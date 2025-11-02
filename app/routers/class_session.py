from fastapi import APIRouter
from app.core.database import get_db
from app.dependencies import get_current_admin_user
from app.models.session_attendance import ClassSession
from app.routers.generator import create_crud_router

# Generate base CRUD
base_router = create_crud_router(
    model=ClassSession,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user,
    tag_prefix="Class Session"
)

# Main router
router = APIRouter()
router.include_router(base_router, prefix="")