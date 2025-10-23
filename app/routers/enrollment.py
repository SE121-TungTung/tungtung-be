from fastapi import APIRouter
from app.core.database import get_db
from app.dependencies import get_current_admin_user
from app.models.academic import ClassEnrollment
from app.routers.generator import create_crud_router

# Generate base CRUD
base_router = create_crud_router(
    model=ClassEnrollment,
    db_dependency=get_db,
    auth_dependency=get_current_admin_user
)

# Main router
router = APIRouter(tags=["Classenrollments"])
router.include_router(base_router, prefix="")