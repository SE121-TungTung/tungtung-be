from fastapi import FastAPI
import app.core.database as database
from app.core.config import settings
from app.routers import auth, users, room, course, classes, enrollment, class_session, attendance, schedule, test, message
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from contextlib import asynccontextmanager

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION
    #,
    #openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup: Starting WebSocket Heartbeat...")
    message.manager.start_heartbeat()
    yield
    print("Application shutdown: Stopping WebSocket Heartbeat...")
    if message.manager._heartbeat_task:
        message.manager._heartbeat_task.cancel()

db = database.get_db()

# Set all CORS enabled origins
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )


@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "docs_url": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(room.router)
api_router.include_router(course.router) 
api_router.include_router(classes.router)
api_router.include_router(enrollment.router)
api_router.include_router(class_session.router)
api_router.include_router(attendance.router)
api_router.include_router(schedule.router)
api_router.include_router(message.router)
api_router.include_router(message.base_message_router, prefix="/messages", tags=["Messages (CRUD)"])
api_router.include_router(message.base_recepient_router, prefix="/message-recipients", tags=["MessageRecipients (CRUD)"])
api_router.include_router(test.router)

app.include_router(api_router, prefix="/api/v1")