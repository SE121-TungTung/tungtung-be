from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
import uuid

from app.core.database import get_db
from app.models.lead import Lead, LeadStatus
from app.models.user import UserRole
from app.dependencies import require_role
from app.schemas.base_schema import ApiResponse, PaginationMetadata, PaginationResponse
from pydantic import BaseModel, ConfigDict
from datetime import datetime

router = APIRouter(prefix="/leads", tags=["Admin Leads"])

class LeadResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    phone: Optional[str] = None
    source: Optional[str] = None
    status: LeadStatus
    target_band: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class LeadUpdate(BaseModel):
    status: Optional[LeadStatus] = None
    notes: Optional[str] = None

@router.get("", response_model=PaginationResponse[LeadResponse])
def get_leads(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[LeadStatus] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_role([UserRole.SYSTEM_ADMIN, UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN]))
):
    query = db.query(Lead).filter(Lead.deleted_at.is_(None))
    
    if status:
        query = query.filter(Lead.status == status)
        
    if search:
        query = query.filter(
            Lead.full_name.ilike(f"%{search}%") | 
            Lead.email.ilike(f"%{search}%") |
            Lead.phone.ilike(f"%{search}%")
        )
        
    total = query.count()
    leads = query.order_by(desc(Lead.created_at)).offset((page - 1) * limit).limit(limit).all()
    
    return PaginationResponse(
        data=[LeadResponse.model_validate(lead) for lead in leads],
        meta=PaginationMetadata(
            total=total,
            page=page,
            limit=limit,
            total_pages=(total + limit - 1) // limit
        )
    )

@router.patch("/{lead_id}", response_model=ApiResponse[LeadResponse])
def update_lead(
    lead_id: uuid.UUID = Path(...),
    update_data: LeadUpdate = None,
    db: Session = Depends(get_db),
    _=Depends(require_role([UserRole.SYSTEM_ADMIN, UserRole.OFFICE_ADMIN, UserRole.CENTER_ADMIN]))
):
    lead = db.query(Lead).filter(Lead.id == lead_id, Lead.deleted_at.is_(None)).first()
    if not lead:
        return ApiResponse(success=False, code="NOT_FOUND", message="Lead not found")
        
    if update_data.status is not None:
        lead.status = update_data.status
    if update_data.notes is not None:
        lead.notes = update_data.notes
        
    db.commit()
    db.refresh(lead)
    
    return ApiResponse(data=LeadResponse.model_validate(lead))
