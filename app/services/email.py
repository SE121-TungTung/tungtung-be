import httpx
import logging
from pathlib import Path
from typing import Dict, Any, List
from jinja2 import Environment, FileSystemLoader
from app.core.config import settings

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        # Cấu hình Jinja2 để load template
        template_dir = Path(__file__).parent.parent / 'templates/email'
        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True
        )
        self.api_url = "https://api.resend.com/emails"
        self.headers = {
            "Authorization": f"Bearer {settings.MAIL_PASSWORD}", # Dùng API Key từ config
            "Content-Type": "application/json"
        }

    def _render_template(self, template_name: str, context: Dict[str, Any]) -> str:
        """Helper để render HTML từ template file"""
        try:
            template = self.env.get_template(template_name)
            return template.render(**context)
        except Exception as e:
            logger.error(f"Error rendering template {template_name}: {e}")
            raise e

    async def _send_via_api(self, to_email: str, subject: str, html_content: str) -> bool:
        """Hàm gửi core sử dụng httpx gọi Resend API"""
        payload = {
            "from": f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>",
            "to": [to_email],
            "subject": subject,
            "html": html_content
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload
                )
                
                if response.status_code in [200, 201]:
                    logger.info(f"Email sent successfully to {to_email}. ID: {response.json().get('id')}")
                    return True
                else:
                    logger.error(f"Resend API Error {response.status_code}: {response.text}")
                    return False
            except Exception as e:
                logger.error(f"Failed to call Resend API: {e}")
                return False

    async def send_password_reset_email(self, email: str, username: str, reset_token: str):
        template_body = {
            "username": username,
            "otp_code": reset_token,
            "expires_minutes": 30,
            "app_name": settings.PROJECT_NAME
        }
        
        html_content = self._render_template("otp_reset.html", template_body)
        subject = f"{settings.PROJECT_NAME} - Password Reset Request"
        
        return await self._send_via_api(email, subject, html_content)

    async def send_welcome_email(self, email: str, username: str):
        template_body = {
            "username": username,
            "app_name": settings.PROJECT_NAME,
            "login_url": f"{settings.FRONTEND_URL}/login"
        }
        
        html_content = self._render_template("welcome.html", template_body)
        subject = f"Welcome to {settings.PROJECT_NAME}"
        
        return await self._send_via_api(email, subject, html_content)

    async def send_account_creation_email(self, user_email: str, fullname: str, password: str, user_role: str):
        template_body = {
            "full_name": fullname,
            "user_email": user_email,
            "raw_password": password,
            "user_role": user_role,
            "app_name": settings.PROJECT_NAME,
            "login_url": f"{settings.FRONTEND_URL}/login",
            "current_year": 2025
        }
        
        html_content = self._render_template("user_created.html", template_body)
        subject = "THÔNG BÁO TẠO TÀI KHOẢN MỚI"
        
        return await self._send_via_api(user_email, subject, html_content)

# Initialize service
email_service = EmailService()