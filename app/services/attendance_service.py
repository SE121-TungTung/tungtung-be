import secrets
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, case
from uuid import UUID
from datetime import datetime, timedelta
from fastapi import HTTPException

from app.models.session_attendance import (
    ClassSession, AttendanceRecord, AttendanceStatus, SessionStatus,
)
from app.models.academic import Class, ClassEnrollment, EnrollmentStatus
from app.models.user import User
from app.schemas.attendance import (
    AttendanceResponseItem, BatchAttendanceRequest,
    BatchNoteUpdateRequest, QRTokenResponse,
    StudentAttendanceStats, ClassAttendanceStats, AbsentAlertItem,
    CertificateEligibilityResponse, AttendanceConfigResponse, AttendanceConfigUpdate,
)
from app.core.exceptions import APIException
from app.services.audit_log_service import audit_service
from app.services.system_setting_service import system_setting_service
from app.models.audit_log import AuditAction

# ============================================================
# CONFIG KEYS (convention: attendance.*)
# ============================================================
CONFIG_MIN_RATE        = "attendance.min_rate_percent"
CONFIG_GRACE_PERIOD    = "attendance.grace_period_min"
CONFIG_EARLY_CHECKIN   = "attendance.early_checkin_min"
CONFIG_ALERT_ABSENCE   = "attendance.alert_absence_count"

# Defaults (dùng khi chưa có trong DB)
DEFAULT_MIN_RATE       = 80.0
DEFAULT_GRACE_PERIOD   = 5
DEFAULT_EARLY_CHECKIN  = 15
DEFAULT_ALERT_ABSENCE  = 3


class AttendanceService:

    # ==========================================================
    # HELPERS — Load config
    # ==========================================================

    def _get_config(self, db: Session) -> dict:
        """Load attendance config từ SystemSetting."""
        return {
            "min_rate_percent": system_setting_service.get_setting_float(
                db, CONFIG_MIN_RATE, DEFAULT_MIN_RATE
            ),
            "grace_period_min": system_setting_service.get_setting_int(
                db, CONFIG_GRACE_PERIOD, DEFAULT_GRACE_PERIOD
            ),
            "early_checkin_min": system_setting_service.get_setting_int(
                db, CONFIG_EARLY_CHECKIN, DEFAULT_EARLY_CHECKIN
            ),
            "alert_absence_count": system_setting_service.get_setting_int(
                db, CONFIG_ALERT_ABSENCE, DEFAULT_ALERT_ABSENCE
            ),
        }

    def _get_session_or_404(self, db: Session, session_id: UUID) -> ClassSession:
        session = db.query(ClassSession).filter(ClassSession.id == session_id).first()
        if not session:
            raise APIException(
                status_code=404,
                code="SESSION_NOT_FOUND",
                message="Không tìm thấy buổi học",
            )
        return session

    # ==========================================================
    # 1. GET ATTENDANCE SHEET
    # ==========================================================

    def get_session_attendance_sheet(
        self, db: Session, session_id: UUID
    ) -> List[AttendanceResponseItem]:

        session = self._get_session_or_404(db, session_id)

        results = (
            db.query(
                User.id.label("student_id"),
                User.first_name,
                User.last_name,
                User.avatar_url,
                AttendanceRecord.status,
                AttendanceRecord.late_minutes,
                AttendanceRecord.notes,
                AttendanceRecord.check_in_time,
            )
            .join(ClassEnrollment, ClassEnrollment.student_id == User.id)
            .outerjoin(
                AttendanceRecord,
                and_(
                    AttendanceRecord.student_id == User.id,
                    AttendanceRecord.session_id == session_id,
                ),
            )
            .filter(
                ClassEnrollment.class_id == session.class_id,
                ClassEnrollment.status == EnrollmentStatus.ACTIVE,
            )
            .order_by(User.first_name)
            .all()
        )

        attendance_list = []
        for row in results:
            final_status = row.status if row.status else AttendanceStatus.PRESENT
            full_name = f"{row.first_name} {row.last_name}".strip()

            attendance_list.append(
                AttendanceResponseItem(
                    student_id=row.student_id,
                    student_name=full_name,
                    avatar_url=row.avatar_url,
                    status=final_status,
                    late_minutes=row.late_minutes or 0,
                    notes=row.notes,
                    check_in_time=row.check_in_time,
                )
            )

        return attendance_list

    # ==========================================================
    # 2. BULK MARK ATTENDANCE (có time restriction)
    # ==========================================================

    def bulk_mark_attendance(
        self,
        db: Session,
        session_id: UUID,
        data: BatchAttendanceRequest,
        marker_id: UUID,
    ):
        """
        Lưu hoặc Cập nhật điểm danh (Batch Upsert).
        CHỈ cho phép khi session đang SCHEDULED hoặc IN_PROGRESS.
        """
        session = self._get_session_or_404(db, session_id)

        # ✅ Time restriction: chỉ điểm danh trong tiết học
        if session.status not in (SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS):
            raise APIException(
                status_code=400,
                code="SESSION_NOT_ACTIVE",
                message="Chỉ có thể điểm danh khi tiết học đang diễn ra hoặc chưa bắt đầu. "
                        "Sau khi kết thúc, chỉ có thể cập nhật ghi chú.",
            )

        for item in data.items:
            record = (
                db.query(AttendanceRecord)
                .filter(
                    AttendanceRecord.session_id == session_id,
                    AttendanceRecord.student_id == item.student_id,
                )
                .first()
            )

            late_min = item.late_minutes
            if item.status == AttendanceStatus.LATE and late_min == 0:
                pass  # Có thể tính tự động từ session start_time

            if record:
                record.status = item.status
                record.notes = item.notes
                record.late_minutes = late_min
                record.marked_by = marker_id
                record.check_in_time = item.check_in_time or datetime.now()
            else:
                new_record = AttendanceRecord(
                    session_id=session_id,
                    student_id=item.student_id,
                    status=item.status,
                    marked_by=marker_id,
                    late_minutes=late_min,
                    notes=item.notes,
                    check_in_time=item.check_in_time or datetime.now(),
                )
                db.add(new_record)

        session.attendance_taken = True

        audit_service.log(
            db=db,
            action=AuditAction.UPDATE,
            table_name="class_sessions",
            record_id=session.id,
            user_id=marker_id,
            old_values={"attendance_taken": False},
            new_values={"attendance_taken": True},
        )

        db.commit()
        return {"message": "Điểm danh thành công"}

    # ==========================================================
    # 3. UPDATE NOTES (sau tiết học)
    # ==========================================================

    def update_attendance_notes(
        self,
        db: Session,
        session_id: UUID,
        data: BatchNoteUpdateRequest,
        marker_id: UUID,
    ):
        """
        Cập nhật ghi chú lý do cho attendance records.
        Cho phép ở MỌI trạng thái session (kể cả COMPLETED).
        Chỉ cập nhật notes, KHÔNG thay đổi status.
        """
        self._get_session_or_404(db, session_id)

        updated_count = 0
        for item in data.items:
            record = (
                db.query(AttendanceRecord)
                .filter(
                    AttendanceRecord.session_id == session_id,
                    AttendanceRecord.student_id == item.student_id,
                )
                .first()
            )

            if record:
                record.notes = item.notes
                record.marked_by = marker_id
                updated_count += 1

        db.commit()
        return {
            "message": f"Đã cập nhật ghi chú cho {updated_count} học viên",
            "updated_count": updated_count,
        }

    # ==========================================================
    # 4. QR TOKEN
    # ==========================================================

    def generate_qr_token(
        self, db: Session, session_id: UUID, teacher_id: UUID
    ) -> QRTokenResponse:
        """Tạo QR token cho session để học viên tự điểm danh."""
        session = self._get_session_or_404(db, session_id)

        # Validate: teacher phải là GV của session hoặc lớp
        if session.teacher_id != teacher_id and session.substitute_teacher_id != teacher_id:
            raise APIException(
                status_code=403,
                code="FORBIDDEN",
                message="Bạn không phải giáo viên của buổi học này",
            )

        # Validate: session phải đang hoạt động
        if session.status not in (SessionStatus.SCHEDULED, SessionStatus.IN_PROGRESS):
            raise APIException(
                status_code=400,
                code="SESSION_NOT_ACTIVE",
                message="Chỉ có thể tạo QR khi tiết học chưa kết thúc",
            )

        # Generate unique token
        token = secrets.token_urlsafe(48)  # ~64 chars

        # Expiry = session end time
        session_end_dt = datetime.combine(session.session_date, session.end_time)

        session.qr_token = token
        session.qr_expires_at = session_end_dt
        db.commit()

        return QRTokenResponse(
            session_id=session.id,
            qr_token=token,
            expires_at=session_end_dt,
        )

    # ==========================================================
    # 5. STUDENT SELF CHECK-IN (hỗ trợ QR token)
    # ==========================================================

    def process_student_self_check_in(
        self,
        db: Session,
        student_id: UUID,
        session_id: UUID = None,
        qr_token: str = None,
    ) -> dict:
        config = self._get_config(db)

        # Resolve session from QR token or session_id
        if qr_token:
            session = (
                db.query(ClassSession)
                .filter(
                    ClassSession.qr_token == qr_token,
                )
                .first()
            )
            if not session:
                raise APIException(
                    status_code=400,
                    code="INVALID_QR",
                    message="Mã QR không hợp lệ",
                )
            # Check expiry
            if session.qr_expires_at and datetime.now() > session.qr_expires_at:
                raise APIException(
                    status_code=400,
                    code="QR_EXPIRED",
                    message="Mã QR đã hết hạn",
                )
            session_id = session.id
        else:
            session = self._get_session_or_404(db, session_id)

        # Validate: student thuộc lớp
        enrollment = (
            db.query(ClassEnrollment)
            .filter(
                ClassEnrollment.class_id == session.class_id,
                ClassEnrollment.student_id == student_id,
                ClassEnrollment.status == EnrollmentStatus.ACTIVE,
            )
            .first()
        )
        if not enrollment:
            raise APIException(
                status_code=403,
                code="NOT_ENROLLED",
                message="Bạn không thuộc lớp học này",
            )

        # Validate: chưa điểm danh
        existing_record = (
            db.query(AttendanceRecord)
            .filter(
                AttendanceRecord.session_id == session_id,
                AttendanceRecord.student_id == student_id,
            )
            .first()
        )
        if existing_record:
            return {
                "success": False,
                "status": existing_record.status,
                "check_in_time": existing_record.check_in_time,
                "late_minutes": existing_record.late_minutes,
                "message": "Bạn đã điểm danh rồi.",
            }

        # Time logic
        now = datetime.now()
        session_start_dt = datetime.combine(session.session_date, session.start_time)
        session_end_dt = datetime.combine(session.session_date, session.end_time)

        early_minutes = config["early_checkin_min"]
        earliest_allowed = session_start_dt - timedelta(minutes=early_minutes)
        if now < earliest_allowed:
            raise APIException(
                status_code=400,
                code="CHECKIN_TOO_EARLY",
                message=f"Chưa đến giờ điểm danh. Vui lòng quay lại sau.",
            )

        if now > session_end_dt:
            raise APIException(
                status_code=400,
                code="SESSION_ENDED",
                message="Buổi học đã kết thúc, không thể điểm danh.",
            )

        # Late logic
        late_minutes = 0
        status = AttendanceStatus.PRESENT

        grace_limit = session_start_dt + timedelta(minutes=config["grace_period_min"])
        if now > grace_limit:
            status = AttendanceStatus.LATE
            delta = now - session_start_dt
            late_minutes = int(delta.total_seconds() / 60)

        # Save
        new_record = AttendanceRecord(
            session_id=session_id,
            student_id=student_id,
            marked_by=student_id,
            status=status,
            check_in_time=now,
            late_minutes=late_minutes,
            notes="Tự điểm danh" + (" (QR)" if qr_token else ""),
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return {
            "success": True,
            "status": status,
            "check_in_time": new_record.check_in_time,
            "late_minutes": late_minutes,
            "message": "Điểm danh thành công",
        }

    # ==========================================================
    # 6. ATTENDANCE RATE CALCULATION
    # ==========================================================

    def _count_by_status(
        self, db: Session, student_id: UUID, class_id: UUID
    ) -> dict:
        """Đếm số record theo từng status cho 1 student trong 1 class."""
        results = (
            db.query(
                AttendanceRecord.status,
                func.count(AttendanceRecord.id).label("cnt"),
            )
            .join(ClassSession, ClassSession.id == AttendanceRecord.session_id)
            .filter(
                ClassSession.class_id == class_id,
                AttendanceRecord.student_id == student_id,
            )
            .group_by(AttendanceRecord.status)
            .all()
        )

        counts = {
            AttendanceStatus.PRESENT: 0,
            AttendanceStatus.ABSENT: 0,
            AttendanceStatus.LATE: 0,
            AttendanceStatus.EXCUSED: 0,
        }
        for row in results:
            counts[row.status] = row.cnt

        return counts

    def calculate_stats_rate(self, counts: dict) -> float:
        """
        Tỷ lệ cho thống kê hiển thị:
        (PRESENT + LATE) / (PRESENT + LATE + ABSENT) * 100
        EXCUSED loại trừ hoàn toàn khỏi mẫu.
        """
        present = counts[AttendanceStatus.PRESENT]
        late = counts[AttendanceStatus.LATE]
        absent = counts[AttendanceStatus.ABSENT]

        denominator = present + late + absent
        if denominator == 0:
            return 100.0
        return round((present + late) / denominator * 100, 2)

    def calculate_certificate_rate(self, counts: dict) -> float:
        """
        Tỷ lệ cho certificate eligibility:
        (PRESENT + LATE + EXCUSED) / (PRESENT + LATE + ABSENT + EXCUSED) * 100
        EXCUSED tính như attended.
        """
        present = counts[AttendanceStatus.PRESENT]
        late = counts[AttendanceStatus.LATE]
        absent = counts[AttendanceStatus.ABSENT]
        excused = counts[AttendanceStatus.EXCUSED]

        denominator = present + late + absent + excused
        if denominator == 0:
            return 100.0
        return round((present + late + excused) / denominator * 100, 2)

    # ==========================================================
    # 7. STUDENT ATTENDANCE STATS
    # ==========================================================

    def get_student_attendance_stats(
        self, db: Session, class_id: UUID
    ) -> List[StudentAttendanceStats]:
        """Thống kê điểm danh từng học viên trong 1 lớp."""

        # Lấy config threshold
        config = self._get_config(db)
        min_rate = config["min_rate_percent"]

        # Tổng số buổi đã diễn ra (COMPLETED)
        total_sessions = (
            db.query(func.count(ClassSession.id))
            .filter(
                ClassSession.class_id == class_id,
                ClassSession.status == SessionStatus.COMPLETED,
            )
            .scalar()
            or 0
        )

        # Lấy danh sách học viên ACTIVE
        enrollments = (
            db.query(ClassEnrollment, User)
            .join(User, User.id == ClassEnrollment.student_id)
            .filter(
                ClassEnrollment.class_id == class_id,
                ClassEnrollment.status == EnrollmentStatus.ACTIVE,
            )
            .all()
        )

        result = []
        for enrollment, user in enrollments:
            counts = self._count_by_status(db, user.id, class_id)
            stats_rate = self.calculate_stats_rate(counts)
            cert_rate = self.calculate_certificate_rate(counts)

            full_name = f"{user.first_name} {user.last_name}".strip()

            result.append(
                StudentAttendanceStats(
                    student_id=user.id,
                    student_name=full_name,
                    total_sessions=total_sessions,
                    present_count=counts[AttendanceStatus.PRESENT],
                    absent_count=counts[AttendanceStatus.ABSENT],
                    late_count=counts[AttendanceStatus.LATE],
                    excused_count=counts[AttendanceStatus.EXCUSED],
                    attendance_rate=stats_rate,
                    is_certificate_eligible=(cert_rate >= min_rate),
                )
            )

        return result

    # ==========================================================
    # 8. CLASS ATTENDANCE STATS
    # ==========================================================

    def get_class_attendance_stats(
        self, db: Session, class_id: UUID
    ) -> ClassAttendanceStats:
        """Thống kê tổng hợp điểm danh cho 1 lớp."""

        # Lấy thông tin lớp
        class_obj = db.query(Class).filter(Class.id == class_id).first()
        if not class_obj:
            raise APIException(
                status_code=404, code="CLASS_NOT_FOUND", message="Không tìm thấy lớp học"
            )

        config = self._get_config(db)
        min_rate = config["min_rate_percent"]

        total_sessions = (
            db.query(func.count(ClassSession.id))
            .filter(
                ClassSession.class_id == class_id,
                ClassSession.status == SessionStatus.COMPLETED,
            )
            .scalar()
            or 0
        )

        # Lấy danh sách student ACTIVE
        enrollments = (
            db.query(ClassEnrollment.student_id)
            .filter(
                ClassEnrollment.class_id == class_id,
                ClassEnrollment.status == EnrollmentStatus.ACTIVE,
            )
            .all()
        )

        total_students = len(enrollments)
        below_threshold = 0
        total_rate_sum = 0.0

        for (student_id,) in enrollments:
            counts = self._count_by_status(db, student_id, class_id)
            stats_rate = self.calculate_stats_rate(counts)
            total_rate_sum += stats_rate

            cert_rate = self.calculate_certificate_rate(counts)
            if cert_rate < min_rate:
                below_threshold += 1

        avg_rate = round(total_rate_sum / total_students, 2) if total_students > 0 else 100.0

        return ClassAttendanceStats(
            class_id=class_id,
            class_name=class_obj.name,
            total_sessions_held=total_sessions,
            average_attendance_rate=avg_rate,
            students_below_threshold=below_threshold,
            total_students=total_students,
        )

    # ==========================================================
    # 9. ABSENT ALERTS
    # ==========================================================

    def get_absent_alerts(
        self, db: Session, class_id: UUID = None
    ) -> List[AbsentAlertItem]:
        """Danh sách học viên vắng nhiều (absent_count >= threshold)."""

        config = self._get_config(db)
        threshold = config["alert_absence_count"]

        # Sub-query: đếm ABSENT per student per class
        absent_counts = (
            db.query(
                AttendanceRecord.student_id,
                ClassSession.class_id,
                func.count(AttendanceRecord.id).label("absent_count"),
            )
            .join(ClassSession, ClassSession.id == AttendanceRecord.session_id)
            .filter(AttendanceRecord.status == AttendanceStatus.ABSENT)
        )

        if class_id:
            absent_counts = absent_counts.filter(ClassSession.class_id == class_id)

        absent_counts = (
            absent_counts.group_by(AttendanceRecord.student_id, ClassSession.class_id)
            .having(func.count(AttendanceRecord.id) >= threshold)
            .subquery()
        )

        # Join với User và Class để lấy tên
        results = (
            db.query(
                absent_counts.c.student_id,
                absent_counts.c.class_id,
                absent_counts.c.absent_count,
                User.first_name,
                User.last_name,
                Class.name.label("class_name"),
            )
            .join(User, User.id == absent_counts.c.student_id)
            .join(Class, Class.id == absent_counts.c.class_id)
            .order_by(absent_counts.c.absent_count.desc())
            .all()
        )

        alerts = []
        for row in results:
            full_name = f"{row.first_name} {row.last_name}".strip()
            counts = self._count_by_status(db, row.student_id, row.class_id)
            stats_rate = self.calculate_stats_rate(counts)

            alerts.append(
                AbsentAlertItem(
                    student_id=row.student_id,
                    student_name=full_name,
                    class_id=row.class_id,
                    class_name=row.class_name,
                    absent_count=row.absent_count,
                    attendance_rate=stats_rate,
                )
            )

        return alerts

    # ==========================================================
    # 10. CERTIFICATE ELIGIBILITY
    # ==========================================================

    def check_certificate_eligibility(
        self, db: Session, enrollment_id: UUID
    ) -> CertificateEligibilityResponse:
        """Kiểm tra học viên có đủ điều kiện nhận chứng chỉ ảo không."""

        enrollment = (
            db.query(ClassEnrollment)
            .filter(ClassEnrollment.id == enrollment_id)
            .first()
        )
        if not enrollment:
            raise APIException(
                status_code=404,
                code="ENROLLMENT_NOT_FOUND",
                message="Không tìm thấy đăng ký",
            )

        user = db.query(User).filter(User.id == enrollment.student_id).first()
        class_obj = db.query(Class).filter(Class.id == enrollment.class_id).first()

        config = self._get_config(db)
        min_rate = config["min_rate_percent"]

        counts = self._count_by_status(db, enrollment.student_id, enrollment.class_id)
        cert_rate = self.calculate_certificate_rate(counts)

        full_name = f"{user.first_name} {user.last_name}".strip() if user else "N/A"
        class_name = class_obj.name if class_obj else "N/A"

        return CertificateEligibilityResponse(
            enrollment_id=enrollment_id,
            student_id=enrollment.student_id,
            student_name=full_name,
            class_name=class_name,
            attendance_rate=cert_rate,
            min_rate_required=min_rate,
            is_eligible=(cert_rate >= min_rate),
        )

    # ==========================================================
    # 11. UPDATE ENROLLMENT ATTENDANCE RATE
    # ==========================================================

    def update_enrollment_attendance_rate(
        self, db: Session, class_id: UUID
    ) -> int:
        """
        Cập nhật batch cột attendance_rate trên ClassEnrollment
        cho tất cả học viên trong 1 lớp.
        Trả về số enrollment đã cập nhật.
        """
        enrollments = (
            db.query(ClassEnrollment)
            .filter(
                ClassEnrollment.class_id == class_id,
                ClassEnrollment.status == EnrollmentStatus.ACTIVE,
            )
            .all()
        )

        count = 0
        for enrollment in enrollments:
            counts = self._count_by_status(db, enrollment.student_id, class_id)
            rate = self.calculate_stats_rate(counts)
            enrollment.attendance_rate = rate
            count += 1

        db.commit()
        return count

    # ==========================================================
    # 12. ATTENDANCE CONFIG (CRUD via SystemSetting)
    # ==========================================================

    def get_attendance_config(self, db: Session) -> AttendanceConfigResponse:
        config = self._get_config(db)
        return AttendanceConfigResponse(**config)

    def update_attendance_config(
        self, db: Session, data: AttendanceConfigUpdate
    ) -> AttendanceConfigResponse:
        mapping = {
            "min_rate_percent": (CONFIG_MIN_RATE, "Ngưỡng % tối thiểu cho chứng chỉ"),
            "grace_period_min": (CONFIG_GRACE_PERIOD, "Phút ân hạn trước khi tính LATE"),
            "early_checkin_min": (CONFIG_EARLY_CHECKIN, "Check-in sớm tối đa (phút)"),
            "alert_absence_count": (CONFIG_ALERT_ABSENCE, "Số buổi vắng → alert"),
        }

        update_dict = data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            if field in mapping:
                key, desc = mapping[field]
                system_setting_service.set_setting(db, key, str(value), desc)

        return self.get_attendance_config(db)


attendance_service = AttendanceService()