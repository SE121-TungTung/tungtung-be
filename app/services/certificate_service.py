import os
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors

from app.models.certificate import Certificate
from app.models.user import User
from app.models.academic import Course, Class
from app.schemas.certificate import CertificateCreate
from app.core.exceptions import APIException
from app.core.config import settings

# Setup media directory for certificates
CERTIFICATES_DIR = os.path.join(os.getcwd(), "media", "certificates")
os.makedirs(CERTIFICATES_DIR, exist_ok=True)

class CertificateService:
    def _generate_pdf(self, student_name: str, course_name: str, issue_date: str, code: str) -> str:
        """
        Generates a simple PDF certificate and returns the file path
        """
        filename = f"cert_{code}.pdf"
        filepath = os.path.join(CERTIFICATES_DIR, filename)
        
        c = canvas.Canvas(filepath, pagesize=landscape(A4))
        width, height = landscape(A4)
        
        # Border
        c.setStrokeColor(colors.darkblue)
        c.setLineWidth(10)
        c.rect(0.5 * inch, 0.5 * inch, width - 1 * inch, height - 1 * inch)

        # Title
        c.setFont("Helvetica-Bold", 40)
        c.setFillColor(colors.darkblue)
        c.drawCentredString(width / 2.0, height - 2 * inch, "CERTIFICATE OF COMPLETION")
        
        # Subtitle
        c.setFont("Helvetica", 20)
        c.setFillColor(colors.black)
        c.drawCentredString(width / 2.0, height - 3 * inch, "This is to certify that")
        
        # Student Name
        c.setFont("Helvetica-Bold", 35)
        c.setFillColor(colors.darkred)
        c.drawCentredString(width / 2.0, height - 4 * inch, student_name)
        
        # Text
        c.setFont("Helvetica", 20)
        c.setFillColor(colors.black)
        c.drawCentredString(width / 2.0, height - 5 * inch, "has successfully completed the course")
        
        # Course Name
        c.setFont("Helvetica-Bold", 25)
        c.setFillColor(colors.darkblue)
        c.drawCentredString(width / 2.0, height - 6 * inch, course_name)
        
        # Details
        c.setFont("Helvetica", 14)
        c.setFillColor(colors.black)
        c.drawString(1.5 * inch, 1.5 * inch, f"Date: {issue_date}")
        c.drawString(1.5 * inch, 1.2 * inch, f"Code: {code}")
        
        # Signature Line
        c.line(width - 3 * inch, 1.6 * inch, width - 1.5 * inch, 1.6 * inch)
        c.drawCentredString(width - 2.25 * inch, 1.3 * inch, "Director Signature")
        
        c.save()
        
        # Return a relative URL or path
        return f"/media/certificates/{filename}"

    def create_certificate(self, db: Session, data: CertificateCreate, current_user_id: uuid.UUID) -> Certificate:
        # Verify student
        student = db.query(User).filter(User.id == data.student_id).first()
        if not student:
            raise APIException(status_code=404, code="USER_NOT_FOUND", message="Student not found")
            
        # Verify course
        course = db.query(Course).filter(Course.id == data.course_id).first()
        if not course:
            raise APIException(status_code=404, code="COURSE_NOT_FOUND", message="Course not found")

        # Create record
        cert = Certificate(
            student_id=data.student_id,
            course_id=data.course_id,
            class_id=data.class_id,
            certificate_code=data.certificate_code,
            issue_date=data.issue_date,
            final_score=data.final_score,
            attendance_rate=data.attendance_rate,
            created_by=current_user_id
        )
        db.add(cert)
        db.commit()
        db.refresh(cert)

        # Generate PDF
        pdf_url = self._generate_pdf(
            student_name=student.full_name,
            course_name=course.name,
            issue_date=cert.issue_date.strftime("%B %d, %Y"),
            code=cert.certificate_code
        )
        
        # Update URL
        cert.certificate_url = pdf_url
        db.commit()
        db.refresh(cert)
        
        return cert

    def get_student_certificates(self, db: Session, student_id: uuid.UUID):
        return db.query(Certificate).filter(Certificate.student_id == student_id).all()

certificate_service = CertificateService()
