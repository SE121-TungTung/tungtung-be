from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
from pathlib import Path
from typing import Dict, List
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# Email configuration
conf = ConnectionConfig(
    MAIL_USERNAME=settings.MAIL_USERNAME,
    MAIL_PASSWORD=settings.MAIL_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.MAIL_SERVER,
    MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
    USE_CREDENTIALS=settings.USE_CREDENTIALS,
    VALIDATE_CERTS=settings.VALIDATE_CERTS,
    TEMPLATE_FOLDER=Path(__file__).parent.parent / 'templates/email'
)

class EmailService:
    def __init__(self):
        self.fm = FastMail(conf)
    
    async def send_password_reset_email(
        self, 
        email: str, 
        username: str, 
        reset_token: str
    ):
        """Send password reset email"""
        # reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
        
        # template_body = {
        #     "username": username,
        #     "reset_link": reset_link,
        #     "expires_minutes": settings.RESET_TOKEN_EXPIRE_MINUTES,
        #     "app_name": settings.PROJECT_NAME
        # }
        
        template_body = {
            "username": username,
            "otp_code": reset_token,  # Đổi tên variable
            "expires_minutes": 30,
            "app_name": settings.PROJECT_NAME
        }

        message = MessageSchema(
            subject=f"{settings.PROJECT_NAME} - Password Reset Request",
            recipients=[email],
            template_body=template_body,
            subtype=MessageType.html
        )
        
        try:
            await self.fm.send_message(message, template_name="otp_reset.html")
            logger.info(f"Password reset email sent to {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {email}: {e}")
            return False
    
    async def send_welcome_email(self, email: str, username: str):
        """Send welcome email to new users"""
        template_body = {
            "username": username,
            "app_name": settings.PROJECT_NAME,
            "login_url": f"{settings.FRONTEND_URL}/login"
        }
        
        message = MessageSchema(
            subject=f"Welcome to {settings.PROJECT_NAME}",
            recipients=[email],
            template_body=template_body,
            subtype=MessageType.html
        )
        
        try:
            await self.fm.send_message(message, template_name="welcome.html")
            logger.info(f"Welcome email sent to {email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send welcome email: {e}")
            return False

# Initialize service
email_service = EmailService()