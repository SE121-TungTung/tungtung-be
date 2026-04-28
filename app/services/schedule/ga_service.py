"""
GA Schedule Service
====================
Service integration layer: loads data from DB → converts to GA input →
runs the GA engine → saves results back to DB.

Follows the project's singleton service pattern (db passed per-method).
"""
import logging
import math
from datetime import date, time, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.academic import Class, ClassEnrollment, Room
from app.models.ga_schedule import GARun, GARunStatus, GAScheduleProposal, TeacherUnavailability
from app.models.session_attendance import ClassSession
from app.models.user import User

from app.schemas.ga_schedule import (
    GAApplyResponse,
    GAConflictInfo,
    GARunDetailResponse,
    GARunResponse,
    GAScheduleRequest,
    GASessionProposal,
    TeacherUnavailabilityCreate,
    TeacherUnavailabilityResponse,
)
from app.schemas.base_schema import PaginationMetadata, PaginationResponse

from app.services.schedule.genetic_algorithm import (
    GAClassInput,
    GAConfig,
    GAConstraintInput,
    GARoomInput,
    TimeSlotConfig,
    evaluate_fitness,
    individual_to_session_dicts,
    run_ga,
    _build_lookups,
)

from app.services.notification_service import notification_service
from app.schemas.notification import NotificationCreate
from app.models.notification import NotificationType, NotificationPriority

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

# System time slots — mirrors schedule_service.SYSTEM_TIME_SLOTS
SYSTEM_TIME_SLOTS = [
    TimeSlotConfig(1, time(8, 0), time(9, 30)),
    TimeSlotConfig(2, time(9, 45), time(11, 15)),
    TimeSlotConfig(3, time(13, 0), time(14, 30)),
    TimeSlotConfig(4, time(14, 45), time(16, 15)),
    TimeSlotConfig(5, time(18, 0), time(19, 30)),
    TimeSlotConfig(6, time(19, 45), time(21, 15)),
]


class GAScheduleService:
    """
    Orchestrates GA schedule generation:
      1. Load data from DB
      2. Convert to GA engine inputs
      3. Run GA
      4. Save results to DB
      5. Apply proposals to ClassSession
    """

    # ================================================================
    # RUN GA
    # ================================================================

    def run_ga_schedule(
        self,
        db: Session,
        request: GAScheduleRequest,
    ) -> GARunResponse:
        """
        Create a GA run record, execute the GA, and persist results.

        This method is designed to be called from a BackgroundTask,
        so it manages its own DB session lifecycle for the GA execution part.
        The initial GARun record is created on the caller's session.
        """
        # 1. Create GARun record (status=pending)
        config_dict = {
            "population_size": request.population_size,
            "generations": request.generations,
            "crossover_rate": request.crossover_rate,
            "mutation_rate": request.mutation_rate,
            "elitism_count": 5,
            "tournament_size": 5,
            "weights": {
                "consecutive_limit": request.weight_consecutive_limit,
                "paired_classes": request.weight_paired_classes,
                "time_preference": request.weight_time_preference,
                "room_utilization": request.weight_room_utilization,
                "preserve_existing": request.weight_preserve_existing,
            },
        }

        ga_run = GARun(
            status=GARunStatus.PENDING,
            start_date=request.start_date,
            end_date=request.end_date,
            class_ids=[str(c) for c in request.class_ids] if request.class_ids else None,
            config=config_dict,
        )
        db.add(ga_run)
        db.commit()
        db.refresh(ga_run)

        run_id = ga_run.id

        return GARunResponse(
            run_id=run_id,
            status=ga_run.status.value,
            start_date=ga_run.start_date,
            end_date=ga_run.end_date,
            created_at=ga_run.created_at,
        )

    def execute_ga_background(
        self,
        run_id: UUID,
        request: GAScheduleRequest,
    ) -> None:
        """
        Background task: actually runs the GA engine.
        Uses its own DB session to avoid conflicts with the request session.
        """
        bg_db = SessionLocal()
        try:
            ga_run = bg_db.query(GARun).filter(GARun.id == run_id).first()
            if not ga_run:
                logger.error(f"GA run {run_id} not found for background execution")
                return

            # Mark as running
            ga_run.status = GARunStatus.RUNNING
            ga_run.started_at = datetime.now(timezone.utc)
            bg_db.commit()

            try:
                # Load data
                classes_input, rooms_input, constraints_input = self._load_ga_inputs(
                    bg_db, request
                )

                if not classes_input:
                    raise ValueError("No active classes found to schedule")

                # Build GA config
                ga_config = GAConfig(
                    population_size=request.population_size,
                    generations=request.generations,
                    crossover_rate=request.crossover_rate,
                    mutation_rate=request.mutation_rate,
                    weight_consecutive_limit=request.weight_consecutive_limit,
                    weight_paired_classes=request.weight_paired_classes,
                    weight_time_preference=request.weight_time_preference,
                    weight_room_utilization=request.weight_room_utilization,
                    weight_preserve_existing=request.weight_preserve_existing,
                )

                # Run GA engine
                result = run_ga(
                    classes=classes_input,
                    rooms=rooms_input,
                    constraints=constraints_input,
                    config=ga_config,
                    time_slots_config=SYSTEM_TIME_SLOTS,
                    date_range=(request.start_date, request.end_date),
                )

                # Convert result to session dicts
                lookups = _build_lookups(
                    classes_input, rooms_input, constraints_input,
                    SYSTEM_TIME_SLOTS, (request.start_date, request.end_date),
                )
                session_dicts = individual_to_session_dicts(result.best_individual, lookups)

                # Save proposals to DB
                conflict_count = 0
                for sd in session_dicts:
                    proposal = GAScheduleProposal(
                        ga_run_id=run_id,
                        class_id=sd["class_id"],
                        teacher_id=sd["teacher_id"],
                        room_id=sd["room_id"],
                        session_date=sd["session_date"],
                        time_slots=sd["time_slots"],
                        start_time=sd["start_time"],
                        end_time=sd["end_time"],
                        lesson_topic=sd.get("lesson_topic"),
                        is_conflict=sd["is_conflict"],
                        conflict_details=sd.get("conflict_details"),
                    )
                    bg_db.add(proposal)
                    if sd["is_conflict"]:
                        conflict_count += 1

                # Update GA run with results
                ga_run.status = GARunStatus.COMPLETED
                ga_run.best_fitness = result.fitness
                ga_run.hard_violations = result.hard_violations
                ga_run.soft_score = result.soft_score
                ga_run.generations_run = result.generations_run
                ga_run.completed_at = datetime.now(timezone.utc)
                ga_run.result_summary = {
                    "total_sessions": len(session_dicts),
                    "conflict_count": conflict_count,
                    "statistics": {
                        "success_rate": round(
                            (len(session_dicts) - conflict_count) / max(len(session_dicts), 1) * 100, 2
                        ),
                        "classes_scheduled": len(set(sd["class_id"] for sd in session_dicts)),
                        "teachers_scheduled": len(set(sd["teacher_id"] for sd in session_dicts)),
                        "rooms_used": len(set(sd["room_id"] for sd in session_dicts if sd["room_id"])),
                    },
                }

                bg_db.commit()
                logger.info(f"GA run {run_id} completed: {len(session_dicts)} sessions, {conflict_count} conflicts")

            except Exception as e:
                logger.exception(f"GA run {run_id} failed: {e}")
                ga_run.status = GARunStatus.FAILED
                ga_run.error_message = str(e)
                ga_run.completed_at = datetime.now(timezone.utc)
                bg_db.commit()

        except Exception as e:
            logger.exception(f"GA background task critical error: {e}")
        finally:
            bg_db.close()

    # ================================================================
    # QUERY RESULTS
    # ================================================================

    def get_run_result(self, db: Session, run_id: UUID) -> GARunDetailResponse:
        """Get detailed result of a GA run including all proposals."""
        ga_run = db.query(GARun).filter(GARun.id == run_id, GARun.deleted_at.is_(None)).first()
        if not ga_run:
            raise HTTPException(404, "GA run not found")

        # Load proposals with relationships
        proposals = (
            db.query(GAScheduleProposal)
            .filter(GAScheduleProposal.ga_run_id == run_id)
            .all()
        )

        # Build session proposals with names
        sessions = []
        conflicts = []
        for p in proposals:
            # Get names via relationships
            cls = db.query(Class).filter(Class.id == p.class_id).first()
            teacher = db.query(User).filter(User.id == p.teacher_id).first()
            room = db.query(Room).filter(Room.id == p.room_id).first() if p.room_id else None

            session_item = GASessionProposal(
                id=p.id,
                class_id=p.class_id,
                class_name=cls.name if cls else "Unknown",
                teacher_id=p.teacher_id,
                teacher_name=f"{teacher.first_name} {teacher.last_name}" if teacher else "Unknown",
                room_id=p.room_id,
                room_name=room.name if room else None,
                session_date=p.session_date,
                time_slots=p.time_slots,
                start_time=p.start_time,
                end_time=p.end_time,
                lesson_topic=p.lesson_topic,
                is_conflict=p.is_conflict,
                conflict_details=p.conflict_details,
            )
            sessions.append(session_item)

            if p.is_conflict and p.conflict_details:
                conflicts.append(GAConflictInfo(
                    conflict_type=p.conflict_details.get("type", "unknown"),
                    entity_id=p.conflict_details.get("teacher_id") or p.conflict_details.get("room_id"),
                    entity_name=None,
                    session_date=p.session_date,
                    time_slots=p.time_slots,
                    reason=p.conflict_details.get("reason", ""),
                ))

        summary = ga_run.result_summary or {}

        return GARunDetailResponse(
            run_id=ga_run.id,
            status=ga_run.status.value if isinstance(ga_run.status, GARunStatus) else ga_run.status,
            best_fitness=ga_run.best_fitness,
            hard_violations=ga_run.hard_violations,
            soft_score=ga_run.soft_score,
            total_sessions=summary.get("total_sessions", len(sessions)),
            conflict_count=summary.get("conflict_count", len(conflicts)),
            generations_run=ga_run.generations_run,
            start_date=ga_run.start_date,
            end_date=ga_run.end_date,
            started_at=ga_run.started_at,
            completed_at=ga_run.completed_at,
            created_at=ga_run.created_at,
            sessions=sessions,
            conflicts=conflicts,
            statistics=summary.get("statistics", {}),
            config=ga_run.config or {},
        )

    def get_run_history(
        self, db: Session, page: int = 1, limit: int = 20,
    ) -> PaginationResponse[GARunResponse]:
        """Get paginated list of GA runs."""
        query = db.query(GARun).filter(GARun.deleted_at.is_(None))
        total = query.count()

        runs = (
            query
            .order_by(GARun.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        items = []
        for r in runs:
            summary = r.result_summary or {}
            items.append(GARunResponse(
                run_id=r.id,
                status=r.status.value if isinstance(r.status, GARunStatus) else r.status,
                best_fitness=r.best_fitness,
                hard_violations=r.hard_violations,
                soft_score=r.soft_score,
                total_sessions=summary.get("total_sessions"),
                conflict_count=summary.get("conflict_count"),
                generations_run=r.generations_run,
                start_date=r.start_date,
                end_date=r.end_date,
                started_at=r.started_at,
                completed_at=r.completed_at,
                created_at=r.created_at,
            ))

        return PaginationResponse(
            data=items,
            meta=PaginationMetadata(
                page=page,
                limit=limit,
                total=total,
                total_pages=math.ceil(total / limit) if limit > 0 else 0,
            ),
        )

    # ================================================================
    # APPLY PROPOSAL
    # ================================================================

    def apply_ga_proposal(self, db: Session, run_id: UUID) -> GAApplyResponse:
        """
        Admin confirms: apply GA proposal into real ClassSession records.

        Steps:
            1. Load proposals from ga_schedule_proposals
            2. Re-check for conflicts in real-time
            3. Create ClassSession records
            4. Send notifications
            5. Update ga_runs status → applied
        """
        ga_run = db.query(GARun).filter(GARun.id == run_id, GARun.deleted_at.is_(None)).first()
        if not ga_run:
            raise HTTPException(404, "GA run not found")

        if isinstance(ga_run.status, GARunStatus):
            status_val = ga_run.status
        else:
            status_val = GARunStatus(ga_run.status)

        if status_val != GARunStatus.COMPLETED:
            raise HTTPException(
                400,
                f"GA run phải ở trạng thái 'completed' để apply. Trạng thái hiện tại: {status_val.value}"
            )

        # Load proposals
        proposals = (
            db.query(GAScheduleProposal)
            .filter(GAScheduleProposal.ga_run_id == run_id)
            .all()
        )

        if not proposals:
            raise HTTPException(400, "No proposals found for this GA run")

        # Check for hard conflicts
        conflict_proposals = [p for p in proposals if p.is_conflict]
        if conflict_proposals:
            raise HTTPException(
                409,
                f"Không thể apply: còn {len(conflict_proposals)} sessions có xung đột cứng. "
                f"Vui lòng chạy lại GA hoặc xóa các sessions có conflict."
            )

        # Create ClassSession records
        created_sessions = []
        try:
            for p in proposals:
                session = ClassSession(
                    class_id=p.class_id,
                    teacher_id=p.teacher_id,
                    room_id=p.room_id,
                    session_date=p.session_date,
                    start_time=p.start_time,
                    end_time=p.end_time,
                    time_slots=p.time_slots,
                    topic=p.lesson_topic,
                    status="scheduled",
                )
                db.add(session)
                created_sessions.append(session)

            # Update GA run status
            ga_run.status = GARunStatus.APPLIED

            # Update classes.preferred_slots with the new weekly pattern
            self._update_class_preferred_slots(db, proposals)

            db.commit()

            # Send notifications in a separate session to avoid blocking
            self._send_apply_notifications(created_sessions)

            return GAApplyResponse(
                success=True,
                created_count=len(created_sessions),
                message=f"Đã tạo {len(created_sessions)} buổi học từ GA proposal",
                applied_run_id=run_id,
            )

        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error applying GA proposal: {e}")
            raise HTTPException(500, f"Failed to apply GA proposal: {str(e)}")

    def _send_apply_notifications(self, created_sessions: list) -> None:
        """Send notifications to teachers and students after applying GA proposal."""
        noti_db = SessionLocal()
        try:
            students_cache: Dict[UUID, list] = {}

            for session in created_sessions:
                # Notify teacher
                cls = noti_db.query(Class).filter(Class.id == session.class_id).first()
                class_name = cls.name if cls else "Unknown"

                teacher_noti = NotificationCreate(
                    user_id=session.teacher_id,
                    title="Lịch dạy mới đã được xếp (GA)",
                    content=(
                        f"Bạn có buổi dạy lớp {class_name} "
                        f"vào {session.session_date} "
                        f"{session.start_time}-{session.end_time}"
                    ),
                    notification_type=NotificationType.SCHEDULE_CHANGE,
                    priority=NotificationPriority.NORMAL,
                    action_url="",
                )
                notification_service.send_notification_sync(db=noti_db, noti_info=teacher_noti)

                # Notify students
                if session.class_id not in students_cache:
                    students_cache[session.class_id] = (
                        noti_db.query(User)
                        .join(ClassEnrollment, ClassEnrollment.student_id == User.id)
                        .filter(
                            ClassEnrollment.class_id == session.class_id,
                            User.deleted_at.is_(None),
                            ClassEnrollment.deleted_at.is_(None),
                        )
                        .all()
                    )

                for student in students_cache[session.class_id]:
                    student_noti = NotificationCreate(
                        user_id=student.id,
                        title="Lịch học mới (GA)",
                        content=(
                            f"Lớp {class_name} có buổi học "
                            f"vào {session.session_date} "
                            f"{session.start_time}-{session.end_time}"
                        ),
                        notification_type=NotificationType.SCHEDULE_CHANGE,
                        priority=NotificationPriority.NORMAL,
                        action_url="",
                    )
                    notification_service.send_notification_sync(db=noti_db, noti_info=student_noti)

        except Exception as e:
            logger.error(f"Error sending GA apply notifications: {e}")
        finally:
            noti_db.close()

    # ================================================================
    # DELETE RUN
    # ================================================================

    def delete_run(self, db: Session, run_id: UUID) -> Dict[str, Any]:
        """Soft delete a GA run and its proposals."""
        ga_run = db.query(GARun).filter(GARun.id == run_id, GARun.deleted_at.is_(None)).first()
        if not ga_run:
            raise HTTPException(404, "GA run not found")

        if isinstance(ga_run.status, GARunStatus):
            status_val = ga_run.status
        else:
            status_val = GARunStatus(ga_run.status)

        if status_val == GARunStatus.APPLIED:
            raise HTTPException(400, "Không thể xóa GA run đã được apply")

        # Soft delete the run (cascade will handle proposals via relationship)
        ga_run.deleted_at = datetime.now(timezone.utc)

        # Also soft-delete proposals
        proposals = db.query(GAScheduleProposal).filter(
            GAScheduleProposal.ga_run_id == run_id
        ).all()
        for p in proposals:
            p.deleted_at = datetime.now(timezone.utc)

        db.commit()

        return {"success": True, "message": f"Đã xóa GA run {run_id}"}

    # ================================================================
    # TEACHER UNAVAILABILITY CRUD
    # ================================================================

    def create_teacher_unavailability(
        self, db: Session, data: TeacherUnavailabilityCreate,
    ) -> TeacherUnavailabilityResponse:
        """Create a teacher unavailability record."""
        # Validate teacher exists
        teacher = db.query(User).filter(User.id == data.teacher_id, User.deleted_at.is_(None)).first()
        if not teacher:
            raise HTTPException(404, "Teacher not found")

        record = TeacherUnavailability(
            teacher_id=data.teacher_id,
            unavailable_date=data.unavailable_date,
            time_slots=data.time_slots,
            reason=data.reason,
            is_recurring=data.is_recurring,
            day_of_week=data.day_of_week,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return TeacherUnavailabilityResponse.model_validate(record)

    def get_teacher_unavailability(
        self, db: Session,
        teacher_id: Optional[UUID] = None,
        page: int = 1,
        limit: int = 50,
    ) -> PaginationResponse[TeacherUnavailabilityResponse]:
        """Get teacher unavailability records with optional filter."""
        query = db.query(TeacherUnavailability).filter(
            TeacherUnavailability.deleted_at.is_(None)
        )

        if teacher_id:
            query = query.filter(TeacherUnavailability.teacher_id == teacher_id)

        total = query.count()
        records = (
            query
            .order_by(TeacherUnavailability.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
            .all()
        )

        items = [TeacherUnavailabilityResponse.model_validate(r) for r in records]

        return PaginationResponse(
            data=items,
            meta=PaginationMetadata(
                page=page,
                limit=limit,
                total=total,
                total_pages=math.ceil(total / limit) if limit > 0 else 0,
            ),
        )

    def delete_teacher_unavailability(self, db: Session, record_id: UUID) -> Dict[str, Any]:
        """Soft delete a teacher unavailability record."""
        record = db.query(TeacherUnavailability).filter(
            TeacherUnavailability.id == record_id,
            TeacherUnavailability.deleted_at.is_(None),
        ).first()
        if not record:
            raise HTTPException(404, "Teacher unavailability record not found")

        record.deleted_at = datetime.now(timezone.utc)
        db.commit()

        return {"success": True, "message": "Đã xóa lịch bận"}

    # ================================================================
    # PRIVATE: Load data from DB → GA engine input
    # ================================================================

    def _load_ga_inputs(
        self, db: Session, request: GAScheduleRequest,
    ) -> Tuple[List[GAClassInput], List[GARoomInput], GAConstraintInput]:
        """
        Load all necessary data from DB and convert to GA dataclasses.
        """
        # --- 1. Load classes ---
        query = db.query(Class).filter(
            Class.status == "active",
            Class.deleted_at.is_(None),
        )
        if request.class_ids:
            query = query.filter(Class.id.in_(request.class_ids))

        classes_db = query.all()

        classes_input = []

        # Build preference map from request
        pref_map: Dict[UUID, str] = {}
        if hasattr(request, 'class_preferences') and request.class_preferences:
            for cp in request.class_preferences:
                pref_map[cp.class_id] = cp.preferred_time_period

        for c in classes_db:
            pref_slots = c.preferred_slots or []
            unavail_slots = c.unavailable_slots or []

            if isinstance(pref_slots, str):
                import json
                try:
                    pref_slots = json.loads(pref_slots)
                except Exception:
                    pref_slots = []
            if isinstance(unavail_slots, str):
                import json
                try:
                    unavail_slots = json.loads(unavail_slots)
                except Exception:
                    unavail_slots = []

            # preferred_time_period: 1) request param → 2) infer from preferred_slots → 3) None
            preferred = pref_map.get(c.id)
            if not preferred and pref_slots:
                preferred = self._infer_preferred_period(pref_slots)

            classes_input.append(GAClassInput(
                class_id=c.id,
                class_name=c.name,
                teacher_id=c.teacher_id,
                room_id=c.room_id,
                max_students=c.max_students,
                sessions_per_week=c.sessions_per_week or 2,
                preferred_slots=pref_slots if isinstance(pref_slots, list) else [],
                unavailable_slots=unavail_slots if isinstance(unavail_slots, list) else [],
                preferred_time_period=preferred,
            ))

        # --- 2. Load rooms ---
        rooms_db = db.query(Room).filter(
            Room.status == "available",
            Room.deleted_at.is_(None),
        ).all()

        rooms_input = [
            GARoomInput(room_id=r.id, name=r.name, capacity=r.capacity)
            for r in rooms_db
        ]

        # --- 3. Load constraints ---

        # Teacher unavailability
        teacher_unavail: Dict[UUID, List[Tuple[date, List[int]]]] = {}
        unavail_records = db.query(TeacherUnavailability).filter(
            TeacherUnavailability.deleted_at.is_(None)
        ).all()

        for rec in unavail_records:
            tid = rec.teacher_id
            if tid not in teacher_unavail:
                teacher_unavail[tid] = []

            if rec.is_recurring and rec.day_of_week is not None:
                # Expand recurring to actual dates in the range
                from datetime import timedelta
                d = request.start_date
                while d <= request.end_date:
                    if d.weekday() == rec.day_of_week:
                        teacher_unavail[tid].append((d, rec.time_slots or []))
                    d += timedelta(days=1)
            elif rec.unavailable_date:
                if request.start_date <= rec.unavailable_date <= request.end_date:
                    teacher_unavail[tid].append(
                        (rec.unavailable_date, rec.time_slots or [])
                    )

        # Paired classes from request
        paired: List[Tuple[UUID, UUID]] = []
        if request.paired_class_ids:
            for pair in request.paired_class_ids:
                if len(pair) == 2:
                    paired.append((pair[0], pair[1]))

        # Existing sessions (for preserve-existing soft constraint)
        existing_sessions_db = db.query(ClassSession).filter(
            ClassSession.session_date >= request.start_date,
            ClassSession.session_date <= request.end_date,
            ClassSession.status.in_(["scheduled", "in_progress"]),
            ClassSession.deleted_at.is_(None),
        ).all()

        existing_sessions = [
            {
                "class_id": s.class_id,
                "session_date": s.session_date,
                "time_slots": s.time_slots or [],
                "room_id": s.room_id,
            }
            for s in existing_sessions_db
        ]

        constraints = GAConstraintInput(
            teacher_unavailability=teacher_unavail,
            class_fixed_times={},  # No longer used — preferred_slots is soft
            paired_classes=paired,
            exam_dates={},  # No exam_dates feature yet
            existing_sessions=existing_sessions,
        )

        return classes_input, rooms_input, constraints

    @staticmethod
    def _infer_preferred_period(preferred_slots: list):
        """Suy ra buổi chủ đạo từ preferred_slots JSONB."""
        from app.services.schedule.genetic_algorithm import TIME_PERIODS
        all_slots = []
        for rule in preferred_slots:
            if isinstance(rule, dict):
                all_slots.extend(rule.get("slots", []))
        if not all_slots:
            return None
        slot_set = set(all_slots)
        for period_name, period_slots in TIME_PERIODS.items():
            if slot_set.issubset(period_slots):
                return period_name
        return None

    def _update_class_preferred_slots(self, db, proposals) -> None:
        """Update classes.preferred_slots with the new weekly pattern from GA results."""
        from collections import defaultdict
        from app.services.schedule.genetic_algorithm import DAYS

        class_patterns: Dict[UUID, Dict[str, set]] = defaultdict(lambda: defaultdict(set))
        for p in proposals:
            day_name = DAYS[p.session_date.weekday()]
            for slot in (p.time_slots or []):
                class_patterns[p.class_id][day_name].add(slot)

        for class_id, day_slots in class_patterns.items():
            new_preferred = [
                {"day": day, "slots": sorted(slots)}
                for day, slots in sorted(day_slots.items(), key=lambda x: DAYS.index(x[0]))
            ]
            cls = db.query(Class).filter(Class.id == class_id).first()
            if cls:
                cls.preferred_slots = new_preferred


# Singleton instance
ga_schedule_service = GAScheduleService()
