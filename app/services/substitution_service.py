from sqlalchemy.orm import Session, joinedload
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

        # --- SEND NOTIFICATIONS ---
        try:
            from app.models.user import User, UserRole
            from app.services.notification_service import notification_service
            from app.schemas.notification import NotificationCreate
            from app.models.notification import NotificationType, NotificationPriority
            
            teacher = db.query(User).filter(User.id == current_user_id).first()
            teacher_name = f"{teacher.first_name} {teacher.last_name}" if teacher else "Giáo viên"
            class_name = session.session_class.name if session.session_class else "Lớp học"
            session_date_str = session.session_date.strftime('%d/%m/%Y')
            
            # 1. Notify Center Admins
            admins = db.query(User).filter(User.role == UserRole.CENTER_ADMIN, User.deleted_at == None).all()
            for admin in admins:
                notification_service.send_notification_sync(
                    db,
                    NotificationCreate(
                        user_id=admin.id,
                        title="Yêu cầu dạy thế mới",
                        content=f"Giáo viên {teacher_name} đã gửi yêu cầu dạy thế cho buổi học ngày {session_date_str} (lớp {class_name}).",
                        notification_type=NotificationType.SYSTEM_ALERT,
                        priority=NotificationPriority.NORMAL,
                        action_url="/admin/schedule"
                    )
                )
                
            # 2. Notify Target Substitute if specified
            if new_request.target_substitute_id:
                notification_service.send_notification_sync(
                    db,
                    NotificationCreate(
                        user_id=new_request.target_substitute_id,
                        title="Đề xuất dạy thế",
                        content=f"Bạn được đề xuất dạy thế cho giáo viên {teacher_name} vào ngày {session_date_str} (lớp {class_name}).",
                        notification_type=NotificationType.SYSTEM_ALERT,
                        priority=NotificationPriority.NORMAL,
                        action_url="/teacher/kpi"
                    )
                )
        except Exception as ex:
            print(f"Error sending notifications: {ex}")

        return self._get_request_by_id(db, new_request.id)

    def _get_request_by_id(self, db: Session, request_id: UUID) -> SubstitutionRequest:
        return db.query(SubstitutionRequest).options(
            joinedload(SubstitutionRequest.requesting_teacher),
            joinedload(SubstitutionRequest.target_substitute),
            joinedload(SubstitutionRequest.session).joinedload(ClassSession.session_class)
        ).filter(SubstitutionRequest.id == request_id).first()

    def get_requests(self, db: Session, user_id: UUID, role: str):
        query = db.query(SubstitutionRequest).options(
            joinedload(SubstitutionRequest.requesting_teacher),
            joinedload(SubstitutionRequest.target_substitute),
            joinedload(SubstitutionRequest.session).joinedload(ClassSession.session_class)
        )
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
        
        # Support both flows:
        if req.status == SubstitutionStatus.PENDING:
            # Flow A: Move to ACCEPTED, waiting for admin approval
            if req.target_substitute_id and req.target_substitute_id != substitute_id:
                raise APIException(status_code=403, code="FORBIDDEN", message="This request is targeted to another substitute")
                
            req.status = SubstitutionStatus.ACCEPTED
            if not req.target_substitute_id:
                req.target_substitute_id = substitute_id
            req.updated_by = substitute_id
            
        elif req.status == SubstitutionStatus.ACCEPTED:
            # Flow B: Since admin already approved, this acceptance makes it APPROVED and updates the timetable!
            if req.target_substitute_id != substitute_id:
                raise APIException(status_code=403, code="FORBIDDEN", message="This request is targeted to another substitute")
                
            req.status = SubstitutionStatus.APPROVED
            req.updated_by = substitute_id
            
            # Update ClassSession
            session = db.query(ClassSession).filter(ClassSession.id == req.class_session_id).first()
            if session:
                session.substitute_teacher_id = substitute_id
        else:
            raise APIException(status_code=400, code="INVALID_STATUS", message="Can only accept PENDING or ACCEPTED requests")
            
        db.commit()
        db.refresh(req)

        # --- SEND NOTIFICATIONS ---
        try:
            from app.models.user import User, UserRole
            from app.services.notification_service import notification_service
            from app.schemas.notification import NotificationCreate
            from app.models.notification import NotificationType, NotificationPriority
            
            sub_teacher = db.query(User).filter(User.id == substitute_id).first()
            sub_name = f"{sub_teacher.first_name} {sub_teacher.last_name}" if sub_teacher else "Giáo viên thế"
            session = db.query(ClassSession).filter(ClassSession.id == req.class_session_id).first()
            class_name = session.session_class.name if session and session.session_class else "Lớp học"
            session_date_str = session.session_date.strftime('%d/%m/%Y') if session else ""
            
            # Notify requesting teacher
            notification_service.send_notification_sync(
                db,
                NotificationCreate(
                    user_id=req.requesting_teacher_id,
                    title="Yêu cầu dạy thế được xác nhận",
                    content=f"Giáo viên {sub_name} đã xác nhận đồng ý dạy thế cho buổi học ngày {session_date_str} (lớp {class_name}).",
                    notification_type=NotificationType.SYSTEM_ALERT,
                    priority=NotificationPriority.NORMAL,
                    action_url=f"/teacher/classes/{session.class_id}" if session else None
                )
            )
            
            # Notify admins
            admins = db.query(User).filter(User.role == UserRole.CENTER_ADMIN, User.deleted_at == None).all()
            for admin in admins:
                notification_service.send_notification_sync(
                    db,
                    NotificationCreate(
                        user_id=admin.id,
                        title="GV thế đã nhận lớp",
                        content=f"Giáo viên {sub_name} đã nhận dạy thế cho lớp {class_name} vào ngày {session_date_str}.",
                        notification_type=NotificationType.SYSTEM_ALERT,
                        priority=NotificationPriority.NORMAL,
                        action_url="/admin/schedule"
                    )
                )
        except Exception as ex:
            print(f"Error sending accept notifications: {ex}")

        return self._get_request_by_id(db, req.id)

    def substitute_decline(self, db: Session, request_id: UUID, substitute_id: UUID) -> SubstitutionRequest:
        req = db.query(SubstitutionRequest).filter(SubstitutionRequest.id == request_id).first()
        if not req:
            raise APIException(status_code=404, code="REQUEST_NOT_FOUND", message="Substitution request not found")
        
        if req.status not in [SubstitutionStatus.PENDING, SubstitutionStatus.ACCEPTED]:
            raise APIException(status_code=400, code="INVALID_STATUS", message="Can only decline PENDING or ACCEPTED requests")
            
        if req.target_substitute_id != substitute_id:
            raise APIException(status_code=403, code="FORBIDDEN", message="You are not the target substitute for this request")

        req.status = SubstitutionStatus.DECLINED
        req.updated_by = substitute_id
        db.commit()
        db.refresh(req)

        # --- SEND NOTIFICATIONS ---
        try:
            from app.models.user import User
            from app.services.notification_service import notification_service
            from app.schemas.notification import NotificationCreate
            from app.models.notification import NotificationType, NotificationPriority
            
            sub_teacher = db.query(User).filter(User.id == substitute_id).first()
            sub_name = f"{sub_teacher.first_name} {sub_teacher.last_name}" if sub_teacher else "Giáo viên thế"
            session = db.query(ClassSession).filter(ClassSession.id == req.class_session_id).first()
            class_name = session.session_class.name if session and session.session_class else "Lớp học"
            session_date_str = session.session_date.strftime('%d/%m/%Y') if session else ""
            
            # Notify requesting teacher
            notification_service.send_notification_sync(
                db,
                NotificationCreate(
                    user_id=req.requesting_teacher_id,
                    title="Đề xuất dạy thế bị từ chối",
                    content=f"Giáo viên {sub_name} đã từ chối đề xuất dạy thế cho buổi học ngày {session_date_str} (lớp {class_name}).",
                    notification_type=NotificationType.SYSTEM_ALERT,
                    priority=NotificationPriority.NORMAL,
                    action_url=f"/teacher/classes/{session.class_id}" if session else None
                )
            )
        except Exception as ex:
            print(f"Error sending decline notifications: {ex}")

        return self._get_request_by_id(db, req.id)

    def admin_approve(self, db: Session, request_id: UUID, admin_id: UUID, target_substitute_id: UUID = None, admin_note: str = None) -> SubstitutionRequest:
        req = db.query(SubstitutionRequest).filter(SubstitutionRequest.id == request_id).first()
        if not req:
            raise APIException(status_code=404, code="REQUEST_NOT_FOUND", message="Substitution request not found")
            
        # Support both flows:
        if req.status == SubstitutionStatus.ACCEPTED:
            # Flow A (Original): Teacher requests -> Substitute accepts (ACCEPTED) -> Admin approves (APPROVED)
            req.status = SubstitutionStatus.APPROVED
            req.resolved_by = admin_id
            req.resolved_at = datetime.utcnow()
            req.admin_note = admin_note
            req.updated_by = admin_id
            
            # Update ClassSession
            session = db.query(ClassSession).filter(ClassSession.id == req.class_session_id).first()
            if session:
                session.substitute_teacher_id = req.target_substitute_id
                
        elif req.status == SubstitutionStatus.PENDING:
            # Flow B (User Spec): Teacher requests (PENDING) -> Admin approves & chooses substitute (ACCEPTED) -> Substitute accepts (APPROVED)
            if target_substitute_id:
                req.target_substitute_id = target_substitute_id
                
            if not req.target_substitute_id:
                raise APIException(status_code=400, code="SUBSTITUTE_REQUIRED", message="Please assign a substitute teacher first")
                
            req.status = SubstitutionStatus.ACCEPTED # Moves to pending teacher acceptance
            req.resolved_by = admin_id
            req.resolved_at = datetime.utcnow()
            req.admin_note = admin_note
            req.updated_by = admin_id
        else:
            raise APIException(status_code=400, code="INVALID_STATUS", message="Request must be PENDING or ACCEPTED to approve")
            
        db.commit()
        db.refresh(req)

        # --- SEND NOTIFICATIONS ---
        try:
            from app.models.user import User
            from app.services.notification_service import notification_service
            from app.schemas.notification import NotificationCreate
            from app.models.notification import NotificationType, NotificationPriority
            
            session = db.query(ClassSession).filter(ClassSession.id == req.class_session_id).first()
            class_name = session.session_class.name if session and session.session_class else "Lớp học"
            session_date_str = session.session_date.strftime('%d/%m/%Y') if session else ""
            
            if req.status == SubstitutionStatus.APPROVED:
                # Notify requesting teacher
                notification_service.send_notification_sync(
                    db,
                    NotificationCreate(
                        user_id=req.requesting_teacher_id,
                        title="Yêu cầu dạy thế được Admin phê duyệt",
                        content=f"Admin đã phê duyệt yêu cầu dạy thế vào ngày {session_date_str} (lớp {class_name}). Lịch dạy đã được cập nhật.",
                        notification_type=NotificationType.SYSTEM_ALERT,
                        priority=NotificationPriority.NORMAL,
                        action_url=f"/teacher/classes/{session.class_id}" if session else None
                    )
                )
                # Notify substitute teacher
                if req.target_substitute_id:
                    notification_service.send_notification_sync(
                        db,
                        NotificationCreate(
                            user_id=req.target_substitute_id,
                            title="Được phê duyệt dạy thế",
                            content=f"Admin đã phê duyệt bạn dạy thế cho buổi học ngày {session_date_str} (lớp {class_name}). Lịch dạy bận đã cập nhật.",
                            notification_type=NotificationType.SYSTEM_ALERT,
                            priority=NotificationPriority.NORMAL,
                            action_url="/teacher/kpi"
                        )
                    )
            elif req.status == SubstitutionStatus.ACCEPTED:
                # Notify substitute teacher
                if req.target_substitute_id:
                    notification_service.send_notification_sync(
                        db,
                        NotificationCreate(
                            user_id=req.target_substitute_id,
                            title="Đề xuất dạy thế được chỉ định từ Admin",
                            content=f"Admin đã chỉ định và phê duyệt bạn dạy thế vào ngày {session_date_str} (lớp {class_name}). Vui lòng xác nhận đồng ý.",
                            notification_type=NotificationType.SYSTEM_ALERT,
                            priority=NotificationPriority.NORMAL,
                            action_url="/teacher/kpi"
                        )
                    )
        except Exception as ex:
            print(f"Error sending approve notifications: {ex}")

        return self._get_request_by_id(db, req.id)

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

        # --- SEND NOTIFICATIONS ---
        try:
            from app.models.user import User
            from app.services.notification_service import notification_service
            from app.schemas.notification import NotificationCreate
            from app.models.notification import NotificationType, NotificationPriority
            
            session = db.query(ClassSession).filter(ClassSession.id == req.class_session_id).first()
            class_name = session.session_class.name if session and session.session_class else "Lớp học"
            session_date_str = session.session_date.strftime('%d/%m/%Y') if session else ""
            
            # Notify requesting teacher
            notification_service.send_notification_sync(
                db,
                NotificationCreate(
                    user_id=req.requesting_teacher_id,
                    title="Yêu cầu dạy thế bị Admin từ chối",
                    content=f"Admin đã từ chối yêu cầu dạy thế vào ngày {session_date_str} (lớp {class_name}). Ghi chú: {admin_note or ''}",
                    notification_type=NotificationType.SYSTEM_ALERT,
                    priority=NotificationPriority.NORMAL,
                    action_url=f"/teacher/classes/{session.class_id}" if session else None
                )
            )
            
            # Notify substitute teacher if they had accepted
            if req.target_substitute_id:
                notification_service.send_notification_sync(
                    db,
                    NotificationCreate(
                        user_id=req.target_substitute_id,
                        title="Yêu cầu dạy thế bị Admin từ chối",
                        content=f"Admin đã từ chối yêu cầu dạy thế mà bạn đồng ý nhận vào ngày {session_date_str} (lớp {class_name}). Ghi chú: {admin_note or ''}",
                        notification_type=NotificationType.SYSTEM_ALERT,
                        priority=NotificationPriority.NORMAL,
                        action_url=None
                    )
                )
        except Exception as ex:
            print(f"Error sending reject notifications: {ex}")

        return self._get_request_by_id(db, req.id)

substitution_service = SubstitutionService()
