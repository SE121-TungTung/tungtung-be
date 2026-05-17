from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
import app.core.database as database
from app.core.config import settings
from app.core.exceptions import APIException, api_exception_handler, http_exception_handler, global_exception_handler, validation_exception_handler
from app.routers import (
    auth, users, 
    room, course, classes, enrollment, class_session,
    attendance, schedule, ga_schedule, test, 
    message, notification,
    kpi,
    invoice, payment, report, refund,
    chatbot, audit_log, recommendation,
    substitution, certificate)
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from contextlib import asynccontextmanager
from app.core.redis import redis_manager

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION
    #,
    #openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.add_exception_handler(APIException, api_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Application startup: Starting WebSocket Heartbeat...")
    message.manager.start_heartbeat()
    await redis_manager.init_redis()
    yield
    print("Application shutdown: Stopping WebSocket Heartbeat...")
    if message.manager._heartbeat_task:
        message.manager._heartbeat_task.cancel()
    await redis_manager.close_redis()

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

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(room.router)
api_router.include_router(course.router) 
api_router.include_router(classes.router)
api_router.include_router(enrollment.router)
api_router.include_router(class_session.router)
api_router.include_router(attendance.router)
api_router.include_router(schedule.router)
api_router.include_router(ga_schedule.router)
api_router.include_router(message.router)
api_router.include_router(test.router)
api_router.include_router(notification.router)
api_router.include_router(kpi.router)
api_router.include_router(invoice.router)
api_router.include_router(payment.router)
api_router.include_router(report.router)
api_router.include_router(refund.router)
api_router.include_router(chatbot.router)
api_router.include_router(audit_log.router)
api_router.include_router(recommendation.router)
api_router.include_router(substitution.router)
api_router.include_router(certificate.router)

app.include_router(api_router, prefix="/api/v1")