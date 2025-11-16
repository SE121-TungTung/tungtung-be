# app/services/schedule.py
from sqlalchemy.orm import Session
from fastapi import HTTPException
from typing import List, Tuple, Optional, Dict, Any, Union
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
        
        # Xác định giới hạn slot tối đa
        max_slots_limit = request.max_slots_per_session if request.max_slots_per_session else MAX_SLOT_NUMBER 
        
        # B2: Loop through classes
        for class_obj in classes:
            
            # --- TÍNH TOÁN MỤC TIÊU ---
            sessions_per_week = getattr(class_obj, 'sessions_per_week', 2) 
            target_session_count = math.ceil(sessions_per_week * total_weeks)
            sessions_created_for_class = 0
            
            # B3: Loop through date range
            current_date = request.start_date
            
            while current_date <= request.end_date:
                
                # Điều kiện dừng: Nếu đã tạo đủ số lượng sessions cần thiết
                if sessions_created_for_class >= target_session_count:
                    break 
                
                # 1. Chọn và kiểm tra quy tắc/slots khả dụng
                rule, rule_conflict = self._select_and_validate_rule(
                    class_obj=class_obj,
                    current_date=current_date,
                    max_slots_limit=max_slots_limit,
                    prefer_morning=request.prefer_morning
                )

                if rule_conflict:
                    conflicts.append(rule_conflict)
                    current_date += timedelta(days=1)
                    continue

                if rule:
                    # 2. Thực hiện xếp lịch và kiểm tra tất cả xung đột (DB + Request)
                    result = self._attempt_to_schedule_session(
                        db=db,
                        class_obj=class_obj,
                        current_date=current_date,
                        rule=rule,
                        sessions_created_for_class=sessions_created_for_class,
                        request_conflicts=request.class_conflict,
                        request_teacher_conflicts=request.teacher_conflict
                    )

                    # 3. Xử lý kết quả
                    if isinstance(result, SessionProposal):
                        successful_sessions.append(result)
                        sessions_created_for_class += 1
                    else:
                        conflicts.append(result) # result là ConflictInfo
                
                # Chuyển sang ngày tiếp theo
                current_date += timedelta(days=1)
            
            # --- B4: KIỂM TRA BẤT KHẢ THI ---
            if current_date > request.end_date and sessions_created_for_class < target_session_count:
                raise HTTPException(
                    status_code=409, 
                    detail=f"HARD EXCEPTION: Cannot fulfill target of {target_session_count} sessions for class {class_obj.name} within the given range due to resource conflicts."
                )
        
        # B5: Trả về Proposal
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
    # HELPER
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
    
    def _check_request_conflict(
        self,
        id_to_check: UUID,
        session_date: date,
        time_slots: List[int],
        conflict_map: Optional[Dict[str, Dict[str, List[int]]]]
    ) -> bool:
        """Kiểm tra xung đột với dữ liệu nhập vào (class_conflict/teacher_conflict)."""
        if not conflict_map:
            return False
        
        id_str = str(id_to_check)
        date_str = str(session_date)
        
        if id_str in conflict_map:
            date_conflicts = conflict_map[id_str]
            
            if date_str in date_conflicts:
                forbidden_slots = set(date_conflicts[date_str])
                
                if set(time_slots) & forbidden_slots:
                    return True
                    
        return False
        
    # NEW HELPER: Select and Validate Scheduling Rule
    def _select_and_validate_rule(
        self, 
        class_obj: Class, 
        current_date: date, 
        max_slots_limit: int, 
        prefer_morning: bool
    ) -> Tuple[Optional[Dict], Optional[ConflictInfo]]:
        """Selects a scheduling rule (fixed or random) and validates against max_slots_limit."""
        
        day_name = current_date.strftime('%A').lower()
        is_rules_empty = not class_obj.schedule or len(class_obj.schedule) == 0
        rules_to_use = DEFAULT_SLOTS_TO_TRY if is_rules_empty else class_obj.schedule
        
        rule = None
        conflict_info = None

        matching_rules = [r for r in rules_to_use if r.get('day') == day_name and r.get('slots')]
        if not matching_rules:
            return None, None # No rule for this day

        # Áp dụng max_slots_per_session check (Ràng buộc cứng)
        filtered_rules = [r for r in matching_rules if len(r['slots']) <= max_slots_limit]

        if not filtered_rules:
            # Conflict: Fixed rule violates max_slots. Chỉ báo cáo nếu là quy tắc cố định.
            if not is_rules_empty:
                conflict_info = ConflictInfo(
                    class_id=class_obj.id, class_name=class_obj.name, conflict_type="max_slot_violation",
                    session_date=current_date, time_slots=matching_rules[0]['slots'], 
                    reason=f"Fixed rule violates max_slots_per_session limit ({max_slots_limit})."
                )
            return None, conflict_info
            
        if is_rules_empty:
            # Logic xếp ngẫu nhiên (Ưu tiên mềm)
            if prefer_morning:
                morning_slots_numbers = {1, 2} 
                morning_rules = [r for r in filtered_rules if all(slot in morning_slots_numbers for slot in r['slots'])]
                
                rule = random.choice(morning_rules) if morning_rules else random.choice(filtered_rules)
            else:
                rule = random.choice(filtered_rules)
        else:
            # Dùng quy tắc cố định
            rule = filtered_rules[0]
            
        return rule, None
        
    # NEW HELPER: Attempt to schedule a single session with all checks
    def _attempt_to_schedule_session(
        self,
        db: Session,
        class_obj: Class,
        current_date: date,
        rule: Dict,
        sessions_created_for_class: int,
        request_conflicts: Optional[Dict[str, Dict[str, List[int]]]],
        request_teacher_conflicts: Optional[Dict[str, Dict[str, List[int]]]]
    ) -> Union[SessionProposal, ConflictInfo]:
        """Checks all conflicts for a given rule and creates a SessionProposal if successful."""
        
        time_slots = rule['slots']
        teacher_id = class_obj.teacher_id

        # 0. Check Conflicts from Request (Hard Constraints)
        
        # Check Class Conflict
        if self._check_request_conflict(class_obj.id, current_date, time_slots, request_conflicts):
            return ConflictInfo(
                class_id=class_obj.id, class_name=class_obj.name, conflict_type="request_class_conflict",
                session_date=current_date, time_slots=time_slots, 
                reason="Class is manually marked as unavailable at this time (user input)."
            )

        # Check Teacher Conflict
        if self._check_request_conflict(teacher_id, current_date, time_slots, request_teacher_conflicts):
            return ConflictInfo(
                class_id=class_obj.id, class_name=class_obj.name, conflict_type="request_teacher_conflict",
                session_date=current_date, time_slots=time_slots, 
                reason="Teacher is manually marked as unavailable at this time (user input)."
            )

        # 1. Check Teacher Conflict (from DB)
        if self._check_teacher_conflict(db, teacher_id, current_date, time_slots):
            return ConflictInfo(
                class_id=class_obj.id, class_name=class_obj.name, conflict_type="teacher_busy",
                session_date=current_date, time_slots=time_slots, reason=f"Teacher {teacher_id} is busy (DB conflict)."
            )

        # 2. Find Available Room (Hard Constraint - includes DB conflict check)
        room_id = self._find_available_room(db, current_date, time_slots, class_obj.max_students)
        
        if not room_id:
            return ConflictInfo(
                class_id=class_obj.id, class_name=class_obj.name, conflict_type="room_unavailable",
                session_date=current_date, time_slots=time_slots, reason="No available room found matching capacity."
            )

        # 3. SUCCESS: Create Session Proposal
        start_time, end_time = self._get_time_range(time_slots)
        teacher = self.user_repo.get(db, teacher_id)
        room = self.room_repo.get(db, room_id)
        
        return SessionProposal(
            class_id=class_obj.id, class_name=class_obj.name, teacher_id=teacher_id,
            teacher_name=f"{teacher.first_name} {teacher.last_name}", room_id=room_id,
            room_name=room.name, session_date=current_date, time_slots=time_slots,
            start_time=start_time, end_time=end_time,
            lesson_topic=f"Auto Lesson {sessions_created_for_class + 1} for {class_obj.name}"
        )
    


schedule_service = ScheduleService(
    class_repo=class_repository,
    session_repo=class_session_repository,
    room_repo=room_repository,
    user_repo=user_repository
)
# END OF app/services/schedule.py