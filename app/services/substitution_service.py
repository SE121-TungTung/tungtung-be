from sqlalchemy.orm import Session
from app.models.substitution import SubstitutionRequest, SubstitutionStatus
from app.models.session_attendance import ClassSession
from app.schemas.substitution import SubstitutionRequestCreate
from app.core.exceptions import APIException
from uuid import UUID
from datetime import datetime

class SubstitutionService:
    def create_request(self, db: Session, request_data: SubstitutionRequestCreate, current_user_id: UUID) -> SubstitutionRequest:
        # Check if session exists and belongs to the requesting teacher
        session = db.query(ClassSession).filter(ClassSession.id == request_data.class_session_id).first()
        if not session:
            raise APIException(status_code=404, code="SESSION_NOT_FOUND", message="Class session not found")
            
        if session.teacher_id != current_user_id:
            raise APIException(status_code=403, code="FORBIDDEN", message="You can only request substitution for your own sessions")
            
        # Check if there is already a pending or accepted request for this session
        existing_request = db.query(SubstitutionRequest).filter(
            SubstitutionRequest.class_session_id == request_data.class_session_id,
            SubstitutionRequest.status.in_([SubstitutionStatus.PENDING, SubstitutionStatus.ACCEPTED])
        ).first()
        if existing_request:
            raise APIException(status_code=400, code="REQUEST_EXISTS", message="A pending or accepted substitution request already exists for this session")

        # Create request
        new_request = SubstitutionRequest(
            class_session_id=request_data.class_session_id,
            requesting_teacher_id=current_user_id,
            target_substitute_id=request_data.target_substitute_id,
            reason=request_data.reason,
            status=SubstitutionStatus.PENDING,
            created_by=current_user_id
        )
        db.add(new_request)
        db.commit()
        db.refresh(new_request)
        return new_request

    def get_requests(self, db: Session, user_id: UUID, role: str):
        query = db.query(SubstitutionRequest)
        if role == "teacher":
            # For teacher, return requests they made OR requests where they are the target substitute
            query = query.filter(
                (SubstitutionRequest.requesting_teacher_id == user_id) |
                (SubstitutionRequest.target_substitute_id == user_id) |
                (SubstitutionRequest.target_substitute_id == None) # Open requests
            )
        # Admin can see all
        return query.order_by(SubstitutionRequest.created_at.desc()).all()

    def substitute_accept(self, db: Session, request_id: UUID, substitute_id: UUID) -> SubstitutionRequest:
        req = db.query(SubstitutionRequest).filter(SubstitutionRequest.id == request_id).first()
        if not req:
            raise APIException(status_code=404, code="REQUEST_NOT_FOUND", message="Substitution request not found")
        
        if req.status != SubstitutionStatus.PENDING:
            raise APIException(status_code=400, code="INVALID_STATUS", message="Can only accept PENDING requests")
            
        if req.target_substitute_id and req.target_substitute_id != substitute_id:
            raise APIException(status_code=403, code="FORBIDDEN", message="This request is targeted to another substitute")

        req.status = SubstitutionStatus.ACCEPTED
        if not req.target_substitute_id:
            req.target_substitute_id = substitute_id
            
        req.updated_by = substitute_id
        db.commit()
        db.refresh(req)
        return req

    def substitute_decline(self, db: Session, request_id: UUID, substitute_id: UUID) -> SubstitutionRequest:
        req = db.query(SubstitutionRequest).filter(SubstitutionRequest.id == request_id).first()
        if not req:
            raise APIException(status_code=404, code="REQUEST_NOT_FOUND", message="Substitution request not found")
        
        if req.status != SubstitutionStatus.PENDING:
            raise APIException(status_code=400, code="INVALID_STATUS", message="Can only decline PENDING requests")
            
        if req.target_substitute_id != substitute_id:
            raise APIException(status_code=403, code="FORBIDDEN", message="You are not the target substitute for this request")

        req.status = SubstitutionStatus.DECLINED
        req.updated_by = substitute_id
        db.commit()
        db.refresh(req)
        return req

    def admin_approve(self, db: Session, request_id: UUID, admin_id: UUID, admin_note: str = None) -> SubstitutionRequest:
        req = db.query(SubstitutionRequest).filter(SubstitutionRequest.id == request_id).first()
        if not req:
            raise APIException(status_code=404, code="REQUEST_NOT_FOUND", message="Substitution request not found")
            
        if req.status != SubstitutionStatus.ACCEPTED:
            raise APIException(status_code=400, code="INVALID_STATUS", message="Request must be ACCEPTED by a substitute before admin approval")

        req.status = SubstitutionStatus.APPROVED
        req.resolved_by = admin_id
        req.resolved_at = datetime.utcnow()
        req.admin_note = admin_note
        req.updated_by = admin_id

        # Update ClassSession
        session = db.query(ClassSession).filter(ClassSession.id == req.class_session_id).first()
        if session:
            session.substitute_teacher_id = req.target_substitute_id
            
        db.commit()
        db.refresh(req)
        return req

    def admin_reject(self, db: Session, request_id: UUID, admin_id: UUID, admin_note: str = None) -> SubstitutionRequest:
        req = db.query(SubstitutionRequest).filter(SubstitutionRequest.id == request_id).first()
        if not req:
            raise APIException(status_code=404, code="REQUEST_NOT_FOUND", message="Substitution request not found")
            
        if req.status not in [SubstitutionStatus.PENDING, SubstitutionStatus.ACCEPTED]:
            raise APIException(status_code=400, code="INVALID_STATUS", message="Can only reject PENDING or ACCEPTED requests")

        req.status = SubstitutionStatus.REJECTED
        req.resolved_by = admin_id
        req.resolved_at = datetime.utcnow()
        req.admin_note = admin_note
        req.updated_by = admin_id

        db.commit()
        db.refresh(req)
        return req

substitution_service = SubstitutionService()
