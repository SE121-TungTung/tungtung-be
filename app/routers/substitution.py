from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.core.route import ResponseWrapperRoute
from app.schemas.base_schema import ApiResponse
from app.schemas.substitution import SubstitutionRequestCreate, SubstitutionRequestResponse
from app.services.substitution_service import substitution_service
from app.models.user import User, UserRole
from app.dependencies import get_current_active_user, get_current_teacher_or_admin, get_current_admin_user

router = APIRouter(route_class=ResponseWrapperRoute, prefix="/substitutions", tags=["Substitutions"])

@router.post("", response_model=ApiResponse[SubstitutionRequestResponse], status_code=status.HTTP_201_CREATED)
def create_substitution_request(
    payload: SubstitutionRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teacher_or_admin)
):
    """
    Teacher creates a new substitution request for their own class session.
    """
    request = substitution_service.create_request(db, payload, current_user.id)
    return ApiResponse(data=SubstitutionRequestResponse.model_validate(request))

@router.get("", response_model=ApiResponse[List[SubstitutionRequestResponse]])
def get_substitution_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teacher_or_admin)
):
    """
    Get substitution requests relevant to the user.
    Admin sees all. Teacher sees requests they made or are targeted for.
    """
    role = "admin" if current_user.role in [UserRole.CENTER_ADMIN, UserRole.SYSTEM_ADMIN] else "teacher"
    requests = substitution_service.get_requests(db, current_user.id, role)
    return ApiResponse(data=[SubstitutionRequestResponse.model_validate(r) for r in requests])

@router.post("/{request_id}/accept", response_model=ApiResponse[SubstitutionRequestResponse])
def accept_substitution(
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teacher_or_admin)
):
    """
    Substitute teacher accepts a substitution request.
    """
    request = substitution_service.substitute_accept(db, request_id, current_user.id)
    return ApiResponse(data=SubstitutionRequestResponse.model_validate(request))

@router.post("/{request_id}/decline", response_model=ApiResponse[SubstitutionRequestResponse])
def decline_substitution(
    request_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_teacher_or_admin)
):
    """
    Substitute teacher declines a substitution request.
    """
    request = substitution_service.substitute_decline(db, request_id, current_user.id)
    return ApiResponse(data=SubstitutionRequestResponse.model_validate(request))

@router.post("/{request_id}/approve", response_model=ApiResponse[SubstitutionRequestResponse])
def admin_approve_substitution(
    request_id: UUID,
    admin_note: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Admin approves a substitution request that was accepted by a substitute.
    Updates the ClassSession substitute_teacher_id.
    """
    request = substitution_service.admin_approve(db, request_id, current_user.id, admin_note)
    return ApiResponse(data=SubstitutionRequestResponse.model_validate(request))

@router.post("/{request_id}/reject", response_model=ApiResponse[SubstitutionRequestResponse])
def admin_reject_substitution(
    request_id: UUID,
    admin_note: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """
    Admin rejects a substitution request.
    """
    request = substitution_service.admin_reject(db, request_id, current_user.id, admin_note)
    return ApiResponse(data=SubstitutionRequestResponse.model_validate(request))
