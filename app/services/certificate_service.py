import os
import uuid
from datetime import datetime, date
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

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Setup media directory for certificates and register fonts
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CERTIFICATES_DIR = os.path.join(BACKEND_ROOT, "media", "certificates")
os.makedirs(CERTIFICATES_DIR, exist_ok=True)

FONT_DIR = os.path.join(BACKEND_ROOT, "media", "fonts")
REGULAR_FONT_PATH = os.path.join(FONT_DIR, "Roboto-Regular.ttf")
BOLD_FONT_PATH = os.path.join(FONT_DIR, "Roboto-Bold.ttf")

REGULAR_FONT_NAME = "Helvetica"
BOLD_FONT_NAME = "Helvetica-Bold"

if os.path.exists(REGULAR_FONT_PATH):
    try:
        pdfmetrics.registerFont(TTFont("Roboto", REGULAR_FONT_PATH))
        REGULAR_FONT_NAME = "Roboto"
    except Exception as e:
        print(f"Error registering Roboto: {e}")

if os.path.exists(BOLD_FONT_PATH):
    try:
        pdfmetrics.registerFont(TTFont("Roboto-Bold", BOLD_FONT_PATH))
        BOLD_FONT_NAME = "Roboto-Bold"
    except Exception as e:
        print(f"Error registering Roboto-Bold: {e}")

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
        c.setFont(BOLD_FONT_NAME, 40)
        c.setFillColor(colors.darkblue)
        c.drawCentredString(width / 2.0, height - 2 * inch, "CERTIFICATE OF COMPLETION")
        
        # Subtitle
        c.setFont(REGULAR_FONT_NAME, 20)
        c.setFillColor(colors.black)
        c.drawCentredString(width / 2.0, height - 3 * inch, "This is to certify that")
        
        # Student Name
        c.setFont(BOLD_FONT_NAME, 35)
        c.setFillColor(colors.darkred)
        c.drawCentredString(width / 2.0, height - 4 * inch, student_name)
        
        # Text
        c.setFont(REGULAR_FONT_NAME, 20)
        c.setFillColor(colors.black)
        c.drawCentredString(width / 2.0, height - 5 * inch, "has successfully completed the course")
        
        # Course Name
        c.setFont(BOLD_FONT_NAME, 25)
        c.setFillColor(colors.darkblue)
        c.drawCentredString(width / 2.0, height - 6 * inch, course_name)
        
        # Details
        c.setFont(REGULAR_FONT_NAME, 14)
        c.setFillColor(colors.black)
        c.drawString(1.5 * inch, 1.5 * inch, f"Date: {issue_date}")
        c.drawString(1.5 * inch, 1.2 * inch, f"Code: {code}")
        
        # Signature Line
        c.line(width - 3 * inch, 1.6 * inch, width - 1.5 * inch, 1.6 * inch)
        c.setFont(REGULAR_FONT_NAME, 14)
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

        # Check for duplicate certificate
        if data.class_id:
            existing = db.query(Certificate).filter(
                Certificate.class_id == data.class_id,
                Certificate.student_id == data.student_id
            ).first()
            if existing:
                raise APIException(
                    status_code=400,
                    code="CERTIFICATE_ALREADY_ISSUED",
                    message="Chứng chỉ đã được cấp cho học viên này trong lớp học này."
                )

        # Enforce eligibility validation if class_id is provided
        if data.class_id:
            from app.models.academic import ClassEnrollment
            from app.services.attendance_service import attendance_service
            
            enrollment = db.query(ClassEnrollment).filter(
                ClassEnrollment.class_id == data.class_id,
                ClassEnrollment.student_id == data.student_id
            ).first()
            if not enrollment:
                raise APIException(
                    status_code=400,
                    code="ENROLLMENT_NOT_FOUND",
                    message="Học viên không có trong danh sách lớp học này."
                )
            
            eligibility = attendance_service.check_certificate_eligibility(db, enrollment.id)
            if not eligibility.is_eligible:
                raise APIException(
                    status_code=400,
                    code="STUDENT_NOT_ELIGIBLE",
                    message=f"Học viên không đạt điều kiện nhận chứng chỉ (Điểm: {eligibility.final_grade or 0}/10, Chuyên cần: {eligibility.attendance_rate}%)."
                )

        # Auto-generate certificate_code if not provided
        certificate_code = data.certificate_code
        if not certificate_code:
            from sqlalchemy import func
            current_year = datetime.now().year
            count = db.query(Certificate).filter(func.extract('year', Certificate.issue_date) == current_year).count()
            seq_num = count + 1
            # Ensure uniqueness
            while True:
                candidate = f"LOTUS-{current_year}-{seq_num:05d}"
                exists = db.query(Certificate).filter(Certificate.certificate_code == candidate).first()
                if not exists:
                    certificate_code = candidate
                    break
                seq_num += 1

        issue_date = data.issue_date or date.today()

        # If final_score or attendance_rate not provided, try to read from enrollment
        final_score = data.final_score
        attendance_rate = data.attendance_rate
        if (final_score is None or attendance_rate is None) and data.class_id:
            from app.models.academic import ClassEnrollment
            enrollment = db.query(ClassEnrollment).filter(
                ClassEnrollment.class_id == data.class_id,
                ClassEnrollment.student_id == data.student_id
            ).first()
            if enrollment:
                if final_score is None:
                    final_score = enrollment.final_grade
                if attendance_rate is None:
                    attendance_rate = enrollment.attendance_rate

        # Create record
        cert = Certificate(
            student_id=data.student_id,
            course_id=data.course_id,
            class_id=data.class_id,
            certificate_code=certificate_code,
            issue_date=issue_date,
            final_score=final_score,
            attendance_rate=attendance_rate,
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
