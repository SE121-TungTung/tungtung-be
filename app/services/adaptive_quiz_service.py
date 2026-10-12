"""Service layer for Adaptive Quiz (CAT) sessions and test administration."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.models.adaptive_quiz import (
    AdaptiveQuizResponse,
    AdaptiveQuizSession,
    AdaptiveSessionStatus,
    AdaptiveStopReason,
)
from app.models.test import QuestionBank, QuestionType
from app.models.user import User, UserRole
from app.repositories.adaptive_quiz_repository import (
    AdaptiveQuestionPoolRepository,
    AdaptiveQuizResponseRepository,
    AdaptiveQuizSessionRepository,
)
from app.services.cat_engine import (
    fisher_information,
    is_stopping_condition_met,
    select_next_question,
    theta_to_band,
    update_theta,
)


class AdaptiveQuizService:
    def __init__(self):
        self.session_repo = AdaptiveQuizSessionRepository()
        self.response_repo = AdaptiveQuizResponseRepository()
        self.pool_repo = AdaptiveQuestionPoolRepository()

    def start_session(
        self,
        db: Session,
        current_user: User,
        skill_area: str,
        max_items: int = 20,
    ) -> AdaptiveQuizSession:
        normalized_skill = skill_area.lower().strip()
        if normalized_skill not in ["reading", "listening"]:
            raise APIException(
                status_code=400,
                code="INVALID_SKILL_AREA",
                message="Kỹ năng chỉ hỗ trợ 'reading' hoặc 'listening'",
            )

        # Rate-limiting for guest students (max 3 sessions per day)
        if current_user.role == UserRole.GUEST_STUDENT:
            today_count = self.session_repo.count_today_sessions(db, current_user.id)
            if today_count >= 3:
                raise APIException(
                    status_code=429,
                    code="GUEST_SESSION_LIMIT_EXCEEDED",
                    message="Khách truy cập chỉ được làm tối đa 3 bài test mỗi ngày. Vui lòng đăng ký tài khoản để tiếp tục!",
                )

        # Return existing in-progress session if any (idempotency)
        active_session = self.session_repo.get_active_session(db, current_user.id, normalized_skill)
        if active_session:
            return active_session

        # Estimate theta_0 from previous completed sessions in this skill area
        previous_sessions, _ = self.session_repo.list_by_user(
            db, current_user.id, skill_area=normalized_skill, page=1, page_size=1
        )
        theta_0 = 0.0
        if previous_sessions and previous_sessions[0].theta_final is not None:
            theta_0 = float(previous_sessions[0].theta_final)

        import uuid
        new_session = AdaptiveQuizSession(
            id=uuid.uuid4(),
            user_id=current_user.id,
            skill_area=normalized_skill,
            theta_initial=theta_0,
            theta_current=theta_0,
            se_current=1.0,
            items_administered=0,
            max_items=max_items,
            status=AdaptiveSessionStatus.IN_PROGRESS.value,
            theta_history=[],
            started_at=datetime.now(timezone.utc),
            created_by=current_user.id,
        )

        db.add(new_session)
        db.commit()
        db.refresh(new_session)
        return new_session

    def get_session(
        self, db: Session, current_user: User, session_id: UUID
    ) -> AdaptiveQuizSession:
        session = self.session_repo.get_by_id(db, session_id)
        if not session:
            raise APIException(
                status_code=404,
                code="SESSION_NOT_FOUND",
                message="Không tìm thấy phiên làm bài thích ứng",
            )

        # Ensure ownership unless user is staff / admin
        is_staff = current_user.role in [
            UserRole.SYSTEM_ADMIN,
            UserRole.CENTER_ADMIN,
            UserRole.OFFICE_ADMIN,
            UserRole.TEACHER,
        ]
        if session.user_id != current_user.id and not is_staff:
            raise APIException(
                status_code=403,
                code="PERMISSION_DENIED",
                message="Bạn không có quyền truy cập phiên làm bài này",
            )

        return session

    def list_user_sessions(
        self,
        db: Session,
        current_user: User,
        skill_area: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[AdaptiveQuizSession], int]:
        return self.session_repo.list_by_user(
            db, current_user.id, skill_area=skill_area, page=page, page_size=page_size
        )

    def get_next_question(
        self, db: Session, current_user: User, session_id: UUID
    ) -> Dict[str, Any]:
        session = self.get_session(db, current_user, session_id)

        if session.status != AdaptiveSessionStatus.IN_PROGRESS.value:
            raise APIException(
                status_code=400,
                code="SESSION_NOT_ACTIVE",
                message="Phiên làm bài này đã hoàn thành hoặc hết hạn",
            )

        # Check stopping rule
        should_stop, stop_reason = is_stopping_condition_met(
            se_current=float(session.se_current),
            items_administered=session.items_administered,
            max_items=session.max_items,
        )
        if should_stop:
            self._finalize_session(db, session, stop_reason or "completed")
            raise APIException(
                status_code=400,
                code="SESSION_ALREADY_COMPLETED",
                message="Bài thi đã đạt điều kiện dừng và hoàn tất",
            )

        # Exclude questions already answered in this session
        used_responses = self.response_repo.list_by_session(db, session.id)
        used_ids = [
            getattr(r, "question_id", None) or getattr(r, "id", None)
            for r in used_responses
        ]
        used_ids = [uid for uid in used_ids if uid is not None]

        # Fetch CAT eligible pool
        pool = self.pool_repo.get_cat_pool(db, session.skill_area, exclude_ids=used_ids)
        if not pool:
            # Pool exhausted, finalize session
            self._finalize_session(db, session, "pool_exhausted")
            raise APIException(
                status_code=400,
                code="POOL_EXHAUSTED",
                message="Đã hết câu hỏi thích hợp trong ngân hàng đề, phiên làm bài kết thúc",
            )

        # Select question maximizing Fisher Information
        selection = select_next_question(
            current_theta=float(session.theta_current),
            candidates=pool,
            used_question_ids=[str(qid) for qid in used_ids],
        )

        if not selection:
            self._finalize_session(db, session, "pool_exhausted")
            raise APIException(
                status_code=400,
                code="NO_QUESTION_AVAILABLE",
                message="Không thể chọn câu hỏi tiếp theo",
            )

        selected_item, fisher_info = selection

        return {
            "question_id": selected_item.id,
            "item_position": session.items_administered + 1,
            "title": selected_item.title,
            "question_text": selected_item.question_text,
            "question_type": selected_item.question_type.value
            if hasattr(selected_item.question_type, "value")
            else selected_item.question_type,
            "skill_area": selected_item.skill_area.value
            if hasattr(selected_item.skill_area, "value")
            else selected_item.skill_area,
            "options": selected_item.options,
            "audio_url": selected_item.audio_url,
            "image_url": selected_item.image_url,
            "current_theta": float(session.theta_current),
            "current_se": float(session.se_current),
            "items_administered": session.items_administered,
            "max_items": session.max_items,
        }

    def submit_response(
        self,
        db: Session,
        current_user: User,
        session_id: UUID,
        question_id: UUID,
        response_data: Any,
        time_spent_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        session = self.get_session(db, current_user, session_id)

        if session.status != AdaptiveSessionStatus.IN_PROGRESS.value:
            raise APIException(
                status_code=400,
                code="SESSION_NOT_ACTIVE",
                message="Phiên làm bài này đã hoàn thành hoặc hết hạn",
            )

        # Verify question exists
        question = (
            db.query(QuestionBank)
            .filter(QuestionBank.id == question_id, QuestionBank.deleted_at.is_(None))
            .first()
        )
        if not question:
            raise APIException(
                status_code=404,
                code="QUESTION_NOT_FOUND",
                message="Câu hỏi không tồn tại",
            )

        # Check if already answered
        existing_response = (
            db.query(AdaptiveQuizResponse)
            .filter(
                AdaptiveQuizResponse.session_id == session.id,
                AdaptiveQuizResponse.question_id == question.id,
                AdaptiveQuizResponse.deleted_at.is_(None),
            )
            .first()
        )
        if existing_response:
            raise APIException(
                status_code=400,
                code="QUESTION_ALREADY_ANSWERED",
                message="Câu hỏi này đã được trả lời trong phiên hiện tại",
            )

        # Grade response
        is_correct = self._check_correctness(question, response_data)

        # Snapshot IRT parameters
        a_used = float(question.irt_discrimination)
        b_used = float(question.irt_difficulty)
        c_used = float(question.irt_guessing)

        theta_before = float(session.theta_current)
        se_before = float(session.se_current)

        fisher_info = fisher_information(theta_before, a_used, b_used, c_used)

        # Gather previous responses in session
        past_responses = self.response_repo.list_by_session(db, session.id)
        response_vector = [
            {
                "a": float(r.irt_a_used),
                "b": float(r.irt_b_used),
                "c": float(r.irt_c_used),
                "is_correct": r.is_correct,
            }
            for r in past_responses
        ]
        # Append current response
        response_vector.append(
            {
                "a": a_used,
                "b": b_used,
                "c": c_used,
                "is_correct": is_correct,
            }
        )

        # Compute updated ability and SE
        theta_after, se_after = update_theta(theta_before, response_vector)

        item_position = session.items_administered + 1

        # Record response
        response_record = AdaptiveQuizResponse(
            session_id=session.id,
            question_id=question.id,
            item_position=item_position,
            theta_before=theta_before,
            theta_after=theta_after,
            se_before=se_before,
            se_after=se_after,
            fisher_info_at_selection=round(fisher_info, 6),
            irt_a_used=a_used,
            irt_b_used=b_used,
            irt_c_used=c_used,
            response_data=response_data if isinstance(response_data, dict) else {"answer": response_data},
            is_correct=is_correct,
            time_spent_seconds=time_spent_seconds,
            created_by=current_user.id,
        )
        db.add(response_record)

        # Update session
        session.items_administered = item_position
        session.theta_current = theta_after
        session.se_current = se_after

        # Update theta_history
        history = list(session.theta_history or [])
        history.append(
            {
                "item_position": item_position,
                "theta": theta_after,
                "se": se_after,
                "is_correct": is_correct,
                "question_id": str(question.id),
            }
        )
        session.theta_history = history

        # Check stopping rule
        should_stop, stop_reason = is_stopping_condition_met(
            se_current=se_after,
            items_administered=item_position,
            max_items=session.max_items,
        )

        estimated_band = theta_to_band(theta_after)

        if should_stop:
            session.status = AdaptiveSessionStatus.COMPLETED.value
            session.stop_reason = stop_reason
            session.theta_final = theta_after
            session.se_final = se_after
            session.estimated_band = estimated_band
            session.completed_at = datetime.now(timezone.utc)

        db.commit()

        return {
            "item_position": item_position,
            "is_correct": is_correct,
            "correct_answer": question.correct_answer,
            "explanation": question.explanation,
            "theta_before": theta_before,
            "theta_after": theta_after,
            "se_before": se_before,
            "se_after": se_after,
            "is_finished": should_stop,
            "stop_reason": stop_reason if should_stop else None,
            "estimated_band": estimated_band if should_stop else None,
        }

    def finish_session(
        self,
        db: Session,
        current_user: User,
        session_id: UUID,
        reason: str = "user_quit",
    ) -> Dict[str, Any]:
        session = self.get_session(db, current_user, session_id)
        if session.status != AdaptiveSessionStatus.COMPLETED.value:
            self._finalize_session(db, session, reason)

        return {
            "id": session.id,
            "status": session.status,
            "theta_final": float(session.theta_final or session.theta_current),
            "se_final": float(session.se_final or session.se_current),
            "estimated_band": float(session.estimated_band or theta_to_band(float(session.theta_current))),
            "items_administered": session.items_administered,
            "stop_reason": session.stop_reason or reason,
            "started_at": session.started_at,
            "completed_at": session.completed_at or datetime.now(timezone.utc),
            "theta_history": session.theta_history or [],
        }

    def get_session_responses(
        self, db: Session, current_user: User, session_id: UUID
    ) -> List[Dict[str, Any]]:
        session = self.get_session(db, current_user, session_id)
        responses = self.response_repo.list_by_session(db, session.id)
        result = []
        for r in responses:
            question_title = r.question.title if r.question else f"Câu hỏi #{r.item_position}"
            result.append({
                "id": r.id,
                "item_position": r.item_position,
                "question_id": r.question_id,
                "question_title": question_title,
                "irt_a_used": float(r.irt_a_used),
                "irt_b_used": float(r.irt_b_used),
                "irt_c_used": float(r.irt_c_used),
                "is_correct": r.is_correct,
                "time_spent_seconds": r.time_spent_seconds,
            })
        return result

    def _finalize_session(self, db: Session, session: AdaptiveQuizSession, reason: str):
        final_theta = float(session.theta_current)
        final_se = float(session.se_current)
        session.status = AdaptiveSessionStatus.COMPLETED.value
        session.stop_reason = reason
        session.theta_final = final_theta
        session.se_final = final_se
        session.estimated_band = theta_to_band(final_theta)
        session.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(session)

    def _check_correctness(self, question: QuestionBank, response_data: Any) -> bool:
        if response_data is None:
            return False

        if isinstance(response_data, dict):
            student_answer = str(response_data.get("answer") or response_data.get("value") or "").strip()
        else:
            student_answer = str(response_data).strip()

        correct = str(question.correct_answer or "").strip()

        return student_answer.lower() == correct.lower()
