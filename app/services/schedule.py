# app/services/schedule.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import List, Tuple, Optional, Dict, Any
from datetime import timedelta, date, time
from uuid import UUID
import logging

from app.schemas.schedule import (
    TimeSlot, ScheduleGenerateRequest, ScheduleProposal, 
    SessionProposal, ConflictInfo, SessionCreate, SessionUpdate, SessionResponse,
    WeeklySchedule, WeeklySession
)

from app.models.academic import Room
from app.models.session_attendance import ClassSession
from app.models.academic import Class

from app.repositories.user import user_repository
from app.repositories.room import room_repository
from app.repositories.class_session import class_repository
from app.repositories.class_session import class_session_repository
from app.core import config

import math
import random

DEFAULT_MAX_SLOT_PER_SESSION = config.settings.DEFAULT_MAX_SLOT_PER_SESSION

logger = logging.getLogger(__name__)

# System time slots configuration (Cần được quản lý tốt hơn, nhưng giữ tạm thời)
SYSTEM_TIME_SLOTS = [
    TimeSlot(slot_number=1, start_time=time(8, 0), end_time=time(9, 30)),
    TimeSlot(slot_number=2, start_time=time(9, 45), end_time=time(11, 15)),
    TimeSlot(slot_number=3, start_time=time(13, 0), end_time=time(14, 30)),
    TimeSlot(slot_number=4, start_time=time(14, 45), end_time=time(16, 15)),
    TimeSlot(slot_number=5, start_time=time(18, 0), end_time=time(19, 30)),
    TimeSlot(slot_number=6, start_time=time(19, 45), end_time=time(21, 15)),
]

DEFAULT_SLOTS_TO_TRY = []
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
MAX_SLOT_NUMBER = 6 # Dựa trên SYSTEM_TIME_SLOTS có 6 tiết

for day in DAYS:
    # 1. Khối 1 Tiết
    for start in range(1, MAX_SLOT_NUMBER + 1):
        DEFAULT_SLOTS_TO_TRY.append({'day': day, 'slots': [start]})

    # 2. Khối 2 Tiết liên tiếp
    for start in range(1, MAX_SLOT_NUMBER): # Dừng ở 5 để lấy [5, 6]
        DEFAULT_SLOTS_TO_TRY.append({'day': day, 'slots': [start, start + 1]})
        
    # 3. Khối 3 Tiết liên tiếp
    for start in range(1, MAX_SLOT_NUMBER - 1): # Dừng ở 4 để lấy [4, 5, 6]
        DEFAULT_SLOTS_TO_TRY.append({'day': day, 'slots': [start, start + 1, start + 2]})

class ScheduleService:
    def __init__(self, class_repo, session_repo, room_repo, user_repo):
        # DI: Nhận các Repository instances
        self.class_repo = class_repo
        self.session_repo = session_repo
        self.room_repo = room_repo
        self.user_repo = user_repo

    # =========================================================================
    # CORE HELPERS
    # =========================================================================
    
    def _check_teacher_conflict(
        self, 
        db: Session, 
        teacher_id: UUID,
        session_date: date,
        time_slots: List[int],
        exclude_session_id: UUID = None
    ) -> bool:
        """Kiểm tra teacher có bận vào time slots này không (bằng cách so sánh time_slots)."""
        
        query = db.query(ClassSession).filter(
            ClassSession.teacher_id == teacher_id,
            ClassSession.session_date == session_date,
            ClassSession.status.in_(['scheduled', 'in_progress'])
        )
        
        if exclude_session_id:
            query = query.filter(ClassSession.id != exclude_session_id)
            
        existing_sessions = query.all()
        
        for session in existing_sessions:
            if set(session.time_slots) & set(time_slots):
                return True
                
        return False
    
    def _check_room_conflict(
        self,
        db: Session,
        room_id: UUID,
        session_date: date,
        time_slots: List[int],
        exclude_session_id: UUID = None
    ) -> bool:
        """Kiểm tra phòng có trống không (bằng cách so sánh time_slots)."""
        
        query = db.query(ClassSession).filter(
            ClassSession.room_id == room_id,
            ClassSession.session_date == session_date,
            ClassSession.status.in_(['scheduled', 'in_progress'])
        )
        
        if exclude_session_id:
            query = query.filter(ClassSession.id != exclude_session_id)
            
        existing_sessions = query.all()
        
        for session in existing_sessions:
            if set(session.time_slots) & set(time_slots):
                return True
                
        return False
    
    def _find_available_room(
        self,
        db: Session,
        session_date: date,
        time_slots: List[int],
        min_capacity: int
    ) -> Optional[UUID]:
        """Tìm phòng trống phù hợp (ưu tiên phòng nhỏ nhất)."""
        
        rooms = db.query(Room).filter(
            Room.status == 'available',
            Room.deleted_at == None,
            Room.capacity >= min_capacity
        ).order_by(Room.capacity).all()
        
        for room in rooms:
            if not self._check_room_conflict(db, room.id, session_date, time_slots):
                return room.id
        
        return None
    
    def _get_time_range(self, time_slots: List[int]) -> Tuple[time, time]:
        """Convert time_slots to start_time, end_time"""
        if not time_slots:
            raise ValueError("time_slots cannot be empty")
        
        slots = sorted(time_slots)
        
        start_slot = next(s for s in SYSTEM_TIME_SLOTS if s.slot_number == slots[0])
        end_slot = next(s for s in SYSTEM_TIME_SLOTS if s.slot_number == slots[-1])
        
        return start_slot.start_time, end_slot.end_time
    
    def _suggest_alternatives(
        self, db: Session, class_obj: Class, original_date: date, original_slots: List[int], max_slots: int = DEFAULT_MAX_SLOT_PER_SESSION
    ) -> List[Dict[str, Any]]:
        """AI đề xuất giải pháp thay thế (EX1) - Logic gợi ý được giữ nguyên"""
        suggestions = []
        teacher_id = class_obj.teacher_id
        
        # Suggest 1: Try different time slots same day
        for slot_num in range(1, len(SYSTEM_TIME_SLOTS)):
            alt_slots = [slot_num, slot_num + 1] if slot_num < len(SYSTEM_TIME_SLOTS) else [slot_num]
            
            if alt_slots == original_slots or len(alt_slots) != len(original_slots):
                continue
            
            if not self._check_teacher_conflict(db, teacher_id, original_date, alt_slots):
                room_id = self._find_available_room(db, original_date, alt_slots, class_obj.max_students)
                if room_id:
                    start_time, end_time = self._get_time_range(alt_slots)
                    suggestions.append({
                        "type": "time_shift",
                        "date": str(original_date),
                        "time_slots": alt_slots,
                        "start_time": str(start_time),
                        "end_time": str(end_time),
                        "room_id": str(room_id)
                    })
                    if len(suggestions) >= 2: break
        
        # Suggest 2: Try next day
        next_day = original_date + timedelta(days=1)
        if not self._check_teacher_conflict(db, teacher_id, next_day, original_slots):
            room_id = self._find_available_room(db, next_day, original_slots, class_obj.max_students)
            if room_id:
                start_time, end_time = self._get_time_range(original_slots)
                suggestions.append({
                    "type": "date_shift",
                    "date": str(next_day),
                    "time_slots": original_slots,
                    "room_id": str(room_id)
                })
                
        return suggestions[:3]

    # =========================================================================
    # UC MF.3: AUTO-SCHEDULE (Main Feature)
    # =========================================================================
    
    def generate_schedule(
        self, 
        db: Session, 
        request: ScheduleGenerateRequest
    ) -> ScheduleProposal:
        """
        AI tự động tạo schedule proposal.
        Tính sessions cần thiết và xếp ngẫu nhiên nếu không có quy tắc cố định.
        """
        
        # B1: Get classes to schedule
        query = db.query(Class).filter(Class.status == 'active')
        if request.class_ids:
            query = query.filter(Class.id.in_(request.class_ids))
        
        classes = query.all()
        
        if not classes:
            raise HTTPException(400, "No active classes found to schedule")
        
        successful_sessions = []
        conflicts = []
        
        # Tính tổng số tuần và mục tiêu Sessions tổng thể
        duration_days = (request.end_date - request.start_date).days
        total_weeks = duration_days / 7.0 
        
        # B2: Loop through classes
        for class_obj in classes:
            
            # --- TÍNH TOÁN MỤC TIÊU ---
            # Giả định class_obj.sessions_per_week đã được thêm vào Model
            sessions_per_week = getattr(class_obj, 'sessions_per_week', 2) 
            target_session_count = math.ceil(sessions_per_week * total_weeks)
            
            sessions_created_for_class = 0
            
            # Lấy quy tắc: Dùng quy tắc cố định HOẶC dùng quy tắc ngẫu nhiên mặc định
            is_rules_empty = not class_obj.schedule or len(class_obj.schedule) == 0
            
            if is_rules_empty:
                # Nếu không có quy tắc, dùng danh sách ngẫu nhiên (sẽ được chọn ngẫu nhiên sau)
                rules_to_use = DEFAULT_SLOTS_TO_TRY 
                logger.warning(f"Class {class_obj.id} has no schedule rules. Using random default slots.")
            else:
                rules_to_use = class_obj.schedule
            
            # B3: Loop through date range
            current_date = request.start_date
            
            while current_date <= request.end_date:
                
                # Điều kiện dừng: Nếu đã tạo đủ số lượng sessions cần thiết
                if sessions_created_for_class >= target_session_count:
                    break 
                
                day_name = current_date.strftime('%A').lower()
                
                # --- XỬ LÝ QUY TẮC LỊCH (ĐÃ SỬA) ---
                
                # Xác định giới hạn slot tối đa từ request (Hard Constraint)
                # Dùng MAX_SLOT_NUMBER làm default nếu request không gửi
                max_slots_limit = request.max_slots_per_session if request.max_slots_per_session else MAX_SLOT_NUMBER 
                
                rule = None
                
                if is_rules_empty:
                    # Logic xếp ngẫu nhiên
                    eligible_rules = [r for r in rules_to_use if r['day'] == day_name]
                    
                    if not eligible_rules:
                        current_date += timedelta(days=1)
                        continue
                        
                    # 1. Filter by max_slots_per_session (Ràng buộc cứng)
                    eligible_rules = [r for r in eligible_rules if len(r['slots']) <= max_slots_limit]
                    
                    if not eligible_rules:
                        # Nếu không còn rule nào hợp lệ sau khi lọc max_slots
                        current_date += timedelta(days=1)
                        continue
                        
                    # 2. Prioritize Morning Slots (Ưu tiên mềm)
                    if request.prefer_morning:
                        # Slots 1 (8:00) và 2 (9:45) được coi là buổi sáng
                        morning_slots_numbers = {1, 2} 
                        morning_rules = [r for r in eligible_rules if all(slot in morning_slots_numbers for slot in r['slots'])]
                        
                        if morning_rules:
                            # Ưu tiên chọn ngẫu nhiên từ các slot buổi sáng hợp lệ
                            rule = random.choice(morning_rules)
                        else:
                            # Nếu không có slot buổi sáng hợp lệ, chọn ngẫu nhiên từ tất cả eligible
                            rule = random.choice(eligible_rules)
                    else:
                        # Nếu không ưu tiên buổi sáng, chọn ngẫu nhiên từ tất cả eligible
                        rule = random.choice(eligible_rules) 
                        
                else:
                    # Dùng quy tắc cố định (Ưu tiên)
                    matching_rules = [r for r in rules_to_use if r.get('day') == day_name and r.get('slots')]
                    if not matching_rules:
                        current_date += timedelta(days=1)
                        continue
                        
                    # NEW: Áp dụng max_slots_per_session check cho các fixed rules (Ràng buộc cứng)
                    filtered_rules = [r for r in matching_rules if len(r['slots']) <= max_slots_limit]
                    
                    if not filtered_rules:
                        # Ghi nhận xung đột nếu quy tắc cố định bị vi phạm
                        conflicts.append(ConflictInfo(
                            class_id=class_obj.id, class_name=class_obj.name, conflict_type="max_slot_violation",
                            session_date=current_date, time_slots=matching_rules[0]['slots'], 
                            reason=f"Fixed rule violates max_slots_per_session limit ({max_slots_limit})."
                        ))
                        current_date += timedelta(days=1)
                        continue
                        
                    # Chọn rule đầu tiên hợp lệ sau khi lọc
                    rule = filtered_rules[0]
                
                # -------------------------
                
                # Đảm bảo rule đã được chọn
                if not rule:
                    current_date += timedelta(days=1)
                    continue
                    
                time_slots = rule['slots']
                is_slot_assigned = False

                # 1. Kiểm tra Teacher Conflict (Hard Constraint)
                if self._check_teacher_conflict(db, class_obj.teacher_id, current_date, time_slots):
                    # Báo cáo xung đột và chuyển sang ngày/slot tiếp theo
                    conflicts.append(ConflictInfo(
                        class_id=class_obj.id, class_name=class_obj.name, conflict_type="teacher_busy",
                        session_date=current_date, time_slots=time_slots, reason=f"Teacher {class_obj.teacher_id} is busy."
                    ))
                else:
                    # 2. Tìm Phòng Trống (Hard Constraint)
                    room_id = self._find_available_room(db, current_date, time_slots, class_obj.max_students)
                    
                    if room_id:
                        # THÀNH CÔNG: Gán Slot
                        start_time, end_time = self._get_time_range(time_slots)
                        teacher = self.user_repo.get(db, class_obj.teacher_id)
                        room = self.room_repo.get(db, room_id)

                        successful_sessions.append(SessionProposal(
                            class_id=class_obj.id, class_name=class_obj.name, teacher_id=class_obj.teacher_id,
                            teacher_name=f"{teacher.first_name} {teacher.last_name}", room_id=room_id,
                            room_name=room.name, session_date=current_date, time_slots=time_slots,
                            start_time=start_time, end_time=end_time,
                            lesson_topic=f"Auto Lesson {sessions_created_for_class + 1} for {class_obj.name}"
                        ))
                        sessions_created_for_class += 1
                        is_slot_assigned = True
                    else:
                        # Báo cáo xung đột Phòng
                        conflicts.append(ConflictInfo(
                            class_id=class_obj.id, class_name=class_obj.name, conflict_type="room_unavailable",
                            session_date=current_date, time_slots=time_slots, reason="No available room found matching capacity."
                        ))

                # Chuyển sang ngày tiếp theo
                current_date += timedelta(days=1)
            
            # --- B4: KIỂM TRA BẤT KHẢ THI ---
            # Nếu vòng lặp kết thúc mà chưa đủ target sessions
            if current_date > request.end_date and sessions_created_for_class < target_session_count:
                raise HTTPException(
                    status_code=409, 
                    detail=f"HARD EXCEPTION: Cannot fulfill target of {target_session_count} sessions for class {class_obj.name} within the given range due to resource conflicts."
                )
        
        # B4: Trả về Proposal
        total_attempts = len(successful_sessions) + len(conflicts)
        
        return ScheduleProposal(
            total_classes=len(classes),
            successful_sessions=len(successful_sessions),
            conflict_count=len(conflicts),
            sessions=successful_sessions,
            conflicts=conflicts,
            statistics={
                "success_rate": round(len(successful_sessions) / total_attempts * 100, 2) if total_attempts > 0 else 0
            }
        )
    
    # =========================================================================
    # UC MF.5: APPLY PROPOSAL & UC MF.3.1/3.3/3.4 (CRUD Logic)
    # =========================================================================
    
    def apply_proposal(self, db: Session, proposal: ScheduleProposal) -> Dict[str, Any]:
        """UC MF.5: Admin xác nhận và apply proposal"""
        created_sessions = []
        
        try:
            for session_proposal in proposal.sessions:
                # Không cần tính time range nếu đã có start_time, end_time trong proposal
                
                session_data = {
                    "class_id": session_proposal.class_id,
                    "teacher_id": session_proposal.teacher_id,
                    "room_id": session_proposal.room_id,
                    "session_date": session_proposal.session_date,
                    "start_time": session_proposal.start_time,
                    "end_time": session_proposal.end_time,
                    "time_slots": session_proposal.time_slots,
                    "topic": session_proposal.lesson_topic,
                    "status": "scheduled"
                }
                
                # Sử dụng Repo cơ bản (CRUDBase) để tạo Session
                session = self.session_repo.create(db, obj_in=session_data)
                created_sessions.append(session)
                
            db.commit()
            
            # TODO: Trigger notifications (UC MF.6)
            
            return {
                "success": True,
                "created_count": len(created_sessions),
                "message": f"Đã tạo {len(created_sessions)} buổi học thành công"
            }
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error applying schedule proposal: {e}")
            raise HTTPException(500, "Failed to apply schedule")
        
    def get_weekly_schedule(
        self, 
        db: Session, 
        start_date: date, 
        end_date: date, 
        class_id: Optional[UUID] = None, 
        user_id: Optional[UUID] = None
    ) -> WeeklySchedule:
        
        # 1. Bắt đầu truy vấn ClassSession
        query = db.query(ClassSession).filter(
            ClassSession.session_date >= start_date,
            ClassSession.session_date <= end_date,
            ClassSession.status == 'scheduled' # Chỉ lấy lịch đã xếp
        )
        
        # 2. Lọc theo Lớp học
        if class_id:
            query = query.filter(ClassSession.class_id == class_id)
            
        # 3. Lọc theo Cá nhân (User ID)
        if user_id:
            # Lọc nếu user là giáo viên
            query = query.filter(ClassSession.teacher_id == user_id)
            # TODO: Thêm logic phức tạp để lọc nếu user là học viên
            # Ví dụ: Lọc qua bảng class_enrollments
        
        sessions = query.all()
        
        # 4. Định dạng sang Schema Output
        schedule_data = []
        for session in sessions:
            class_obj = self.class_repo.get(db, session.class_id)
            teacher = self.user_repo.get(db, session.teacher_id)
            room = self.room_repo.get(db, session.room_id)
            
            schedule_data.append(WeeklySession(
                session_id=session.id,
                class_name=class_obj.name,
                teacher_name=f"{teacher.first_name} {teacher.last_name}",
                room_name=room.name if room else "N/A",
                day_of_week=session.session_date.strftime('%A'),
                start_time=session.start_time,
                end_time=session.end_time,
                topic=session.topic
            ))
            
        return WeeklySchedule(schedule=schedule_data)
            
    # ... (Các hàm CRUD thủ công khác giữ nguyên logic)
    
    def create_session_manual(self, db: Session, data: SessionCreate) -> SessionResponse:
        """Tạo session thủ công với conflict check"""
        # ... Logic tìm kiếm phòng và kiểm tra xung đột ...
        
        class_obj = self.class_repo.get(db, data.class_id)
        if not class_obj: raise HTTPException(404, "Class not found")
        
        teacher_id = data.teacher_id or class_obj.teacher_id
        
        if self._check_teacher_conflict(db, teacher_id, data.session_date, data.time_slots):
            raise HTTPException(409, "Teacher has conflict at this time")
        
        room_id = data.room_id
        if not room_id:
            room_id = self._find_available_room(db, data.session_date, data.time_slots, class_obj.max_students)
            if not room_id: raise HTTPException(409, "No available room found")
        elif self._check_room_conflict(db, room_id, data.session_date, data.time_slots):
            raise HTTPException(409, "Room is not available at this time")
            
        start_time, end_time = self._get_time_range(data.time_slots)
        
        session_data = data.model_dump(exclude_unset=True) # Dùng Pydantic V2 dump
        session_data.update({
            "teacher_id": teacher_id, "room_id": room_id, 
            "start_time": start_time, "end_time": end_time,
            "status": "scheduled"
        })
        
        session = self.session_repo.create(db, obj_in=session_data)
        db.commit()
        
        return self._to_response(db, session)

    def update_session(
        self,
        db: Session,
        session_id: UUID,
        update_data: SessionUpdate
    ) -> SessionResponse:
        """Update session với conflict check"""
        from app.models.session_attendance import ClassSession
        
        session = self.session_repo.get(db, session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        
        # Check conflicts if changing time/date
        if update_data.session_date or update_data.time_slots:
            new_date = update_data.session_date or session.session_date
            new_slots = update_data.time_slots or session.time_slots
            teacher_id = update_data.teacher_id or session.teacher_id
            
            if self._check_teacher_conflict(
                db, teacher_id, new_date, new_slots, exclude_session_id=session_id
            ):
                raise HTTPException(409, "Teacher conflict")
            
            if update_data.room_id:
                if self._check_room_conflict(
                    db, update_data.room_id, new_date, new_slots, exclude_session_id=session_id
                ):
                    raise HTTPException(409, "Room conflict")
        
        # Update
        update_dict = update_data.dict(exclude_unset=True)
        
        if update_data.time_slots:
            start_time, end_time = self._get_time_range(update_data.time_slots)
            update_dict['start_time'] = start_time
            update_dict['end_time'] = end_time
        
        updated_session = self.session_repo.update(db, db_obj=session, obj_in=update_dict)
        db.commit()
        
        return self._to_response(db, updated_session)
    
    # =========================================================================
    # UC MF.3.4: DELETE SESSION
    # =========================================================================
    
    def delete_session(
        self,
        db: Session,
        session_id: UUID
    ) -> Dict[str, Any]:
        """Soft delete session"""
        session = self.session_repo.get(db, session_id)
        if not session:
            raise HTTPException(404, "Session not found")
        
        # Soft delete
        self.session_repo.update(db, db_obj=session, obj_in={"status": "cancelled"})
        db.commit()
        
        # TODO: Trigger notification
        
        return {"success": True, "message": "Session cancelled"}
    
    # =========================================================================
    # HELPER: Convert to Response
    # =========================================================================
    
    def _to_response(self, db: Session, session) -> SessionResponse:
        """Convert DB model to response schema"""
        class_obj = self.class_repo.get(db, session.class_id)
        teacher = self.user_repo.get(db, session.teacher_id)
        room = self.room_repo.get(db, session.room_id)
        
        return SessionResponse(
            id=session.id,
            class_id=session.class_id,
            class_name=class_obj.name,
            teacher_id=session.teacher_id,
            teacher_name=f"{teacher.first_name} {teacher.last_name}",
            room_id=session.room_id,
            room_name=room.name,
            session_date=session.session_date,
            start_time=session.start_time,
            end_time=session.end_time,
            time_slots=session.time_slots or [],
            topic=session.topic,
            status=session.status,
            created_at=session.created_at
        )

schedule_service = ScheduleService(
    class_repo=class_repository,
    session_repo=class_session_repository,
    room_repo=room_repository,
    user_repo=user_repository
)
# END OF app/services/schedule.py