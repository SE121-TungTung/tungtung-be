from sqlalchemy.orm import Session
from sqlalchemy import and_
from uuid import UUID
from datetime import datetime
from fastapi import HTTPException
from app.models.session_attendance import ClassSession, AttendanceRecord, AttendanceStatus
from app.schemas.attendance import BatchAttendanceRequest
from app.models.user import User
from app.models.academic import ClassEnrollment, EnrollmentStatus
from datetime import timedelta

from app.models.audit_log import AuditAction
from app.services.audit_log import audit_service

ALLOWED_EARLY_MINUTES = 15  # Được điểm danh sớm 15p
GRACE_PERIOD_MINUTES = 5

class AttendanceService():

    def get_session_attendance_sheet(self, db: Session, session_id: UUID) -> list:

        session = db.query(ClassSession).filter(ClassSession.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        results = db.query(
            User.id.label("student_id"),
            User.first_name,
            User.last_name,
            User.avatar_url,
            AttendanceRecord.status,
            AttendanceRecord.late_minutes,
            AttendanceRecord.notes,
            AttendanceRecord.check_in_time
        ).join(
            ClassEnrollment, ClassEnrollment.student_id == User.id
        ).outerjoin(
            AttendanceRecord, 
            and_(
                AttendanceRecord.student_id == User.id,
                AttendanceRecord.session_id == session_id
            )
        ).filter(
            ClassEnrollment.class_id == session.class_id,
            ClassEnrollment.status == EnrollmentStatus.ACTIVE 
        ).order_by(User.first_name).all()

        attendance_list = []
        for row in results:
            final_status = row.status if row.status else AttendanceStatus.PRESENT
            
            full_name = f"{row.first_name} {row.last_name}".strip()

            attendance_list.append({
                "student_id": row.student_id,
                "student_name": full_name,
                "avatar_url": row.avatar_url,
                "status": final_status,
                "late_minutes": row.late_minutes or 0,
                "notes": row.notes,
                "check_in_time": row.check_in_time
            })
            
        return attendance_list
    
    def bulk_mark_attendance(
            self, 
            db: Session, 
            session_id: UUID, 
            data: BatchAttendanceRequest, 
            marker_id: UUID
        ):
            """
            Lưu hoặc Cập nhật điểm danh (Batch Upsert)
            """
            session = db.query(ClassSession).filter(ClassSession.id == session_id).first()
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")

            # Xử lý từng item
            for item in data.items:
                # Tìm record cũ
                record = db.query(AttendanceRecord).filter(
                    AttendanceRecord.session_id == session_id,
                    AttendanceRecord.student_id == item.student_id
                ).first()

                # Tự động tính late_minutes nếu status là LATE mà chưa nhập phút
                late_min = item.late_minutes
                if item.status == AttendanceStatus.LATE and late_min == 0:
                    # Logic tự động tính dựa trên session.start_time vs check_in_time hiện tại
                    # (Bạn có thể implement thêm logic so sánh thời gian ở đây)
                    pass 

                if record:
                    # UPDATE
                    record.status = item.status
                    record.notes = item.notes
                    record.late_minutes = late_min
                    record.marked_by = marker_id
                    record.check_in_time = item.check_in_time or datetime.now() # Cập nhật time nếu cần
                else:
                    # INSERT (CREATE)
                    new_record = AttendanceRecord(
                        session_id=session_id,
                        student_id=item.student_id,
                        status=item.status,
                        marked_by=marker_id,
                        late_minutes=late_min,
                        notes=item.notes,
                        check_in_time=item.check_in_time or datetime.now()
                    )
                    db.add(new_record)

            # Cập nhật trạng thái session
            session.attendance_taken = True

            audit_service.log(
                db=db,
                action=AuditAction.UPDATE,
                table_name="class_sessions",
                record_id=session.id,
                user_id=marker_id,
                old_values={"attendance_taken": False},
                new_values={"attendance_taken": True}
            )
            
            db.commit()
            return {"message": "Attendance marked successfully"}
    
    def process_student_self_check_in(
        self, db: Session, student_id: UUID, session_id: UUID
    ) -> dict:
        # 1. Lấy thông tin Session
        session = db.query(ClassSession).filter(ClassSession.id == session_id).first()
        if not session:
            raise HTTPException(404, "Session not found")

        # 2. Validate: Học sinh có thuộc lớp này không?
        enrollment = db.query(ClassEnrollment).filter(
            ClassEnrollment.class_id == session.class_id,
            ClassEnrollment.student_id == student_id,
            ClassEnrollment.status == EnrollmentStatus.ACTIVE
        ).first()
        
        if not enrollment:
            raise HTTPException(403, "You are not enrolled in this class")

        # 3. Validate: Đã điểm danh chưa?
        existing_record = db.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == session_id,
            AttendanceRecord.student_id == student_id
        ).first()

        if existing_record:
            # Nếu đã có record, trả về thông báo (hoặc lỗi tùy nghiệp vụ)
            return {
                "success": False,
                "status": existing_record.status,
                "check_in_time": existing_record.check_in_time,
                "late_minutes": existing_record.late_minutes,
                "message": "You have already checked in."
            }

        # 4. Xử lý Thời gian (Time Logic)
        now = datetime.now() # Cần đảm bảo timezone server đồng bộ
        
        # Combine date và time từ DB để ra datetime object
        session_start_dt = datetime.combine(session.session_date, session.start_time)
        session_end_dt = datetime.combine(session.session_date, session.end_time)

        # 4a. Chặn điểm danh quá sớm
        earliest_allowed = session_start_dt - timedelta(minutes=ALLOWED_EARLY_MINUTES)
        if now < earliest_allowed:
            raise HTTPException(400, "Check-in not open yet. Please wait.")

        # 4b. Chặn điểm danh sau khi lớp đã kết thúc (Tùy chọn)
        if now > session_end_dt:
             raise HTTPException(400, "Session has ended. You cannot check in anymore.")

        # 5. Tính toán trạng thái (Late logic)
        late_minutes = 0
        status = AttendanceStatus.PRESENT
        
        # Nếu check-in sau thời gian bắt đầu + ân hạn
        grace_limit = session_start_dt + timedelta(minutes=GRACE_PERIOD_MINUTES)
        
        if now > grace_limit:
            status = AttendanceStatus.LATE
            # Tính số phút trễ (làm tròn)
            delta = now - session_start_dt
            late_minutes = int(delta.total_seconds() / 60)

        # 6. Lưu vào DB
        new_record = AttendanceRecord(
            session_id=session_id,
            student_id=student_id,
            marked_by=student_id,  # Ghi nhận chính học sinh tự điểm danh
            status=status,
            check_in_time=now,
            late_minutes=late_minutes,
            notes="Self check-in"
        )
        
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            "success": True,
            "status": status,
            "check_in_time": new_record.check_in_time,
            "late_minutes": late_minutes,
            "message": "Check-in successful"
        }

attendance_service = AttendanceService()