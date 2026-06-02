from fastapi import APIRouter, Depends, status, Path
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse
from app.schemas.certificate import CertificateCreate, CertificateResponse
from app.services.certificate_service import certificate_service
from app.models.user import User, UserRole
from app.dependencies import get_current_active_user, get_current_admin_user

router = APIRouter(route_class=ResponseWrapperRoute, prefix="/certificates", tags=["Certificates"])

@router.post("", response_model=ApiResponse[CertificateResponse], status_code=status.HTTP_201_CREATED)
def issue_certificate(
    payload: CertificateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Center Admin issues a new certificate for a student.
    The PDF will be generated and the URL stored in the database.
    """
    cert = certificate_service.create_certificate(db, payload, current_user.id)
    return ApiResponse(data=CertificateResponse.model_validate(cert))

@router.get("/students/{student_id}", response_model=ApiResponse[List[CertificateResponse]])
def get_student_certificates(
    student_id: UUID = Path(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get all certificates for a specific student.
    Students can view their own, admins/teachers can view for any student.
    """
    # Simple authorization: if student, must match their own ID. 
    # Real app would have a more complex check.
    if current_user.role == UserRole.STUDENT and current_user.id != student_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="You can only view your own certificates")
        
    certs = certificate_service.get_student_certificates(db, student_id)
    return ApiResponse(data=[CertificateResponse.model_validate(c) for c in certs])
