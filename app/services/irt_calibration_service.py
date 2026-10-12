"""Service layer for IRT item parameter calibration and management."""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.models.test import ContentStatus, DifficultyLevel, QuestionBank, QuestionType
from app.repositories.adaptive_quiz_repository import AdaptiveQuestionPoolRepository


class IRTCalibrationService:
    def __init__(self):
        self.pool_repo = AdaptiveQuestionPoolRepository()

    def list_questions_with_irt(
        self,
        db: Session,
        skill_area: Optional[str] = None,
        calibrated: Optional[bool] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[QuestionBank], int]:
        return self.pool_repo.list_questions(
            db,
            skill_area=skill_area,
            calibrated=calibrated,
            search=search,
            page=page,
            page_size=page_size,
        )

    def update_question_irt(
        self,
        db: Session,
        question_id: UUID,
        a: float,
        b: float,
        c: float,
        is_cat_eligible: bool = True,
    ) -> QuestionBank:
        question = self.pool_repo.update_irt(
            db,
            question_id=question_id,
            a=a,
            b=b,
            c=c,
            calibrated=True,
            is_cat_eligible=is_cat_eligible,
        )
        if not question:
            raise APIException(
                status_code=404,
                code="QUESTION_NOT_FOUND",
                message="Không tìm thấy câu hỏi để hiệu chỉnh",
            )
        return question

    def get_calibration_stats(self, db: Session) -> Dict[str, Any]:
        return self.pool_repo.get_stats(db)

    def trigger_batch_calibration(
        self, db: Session, min_responses: int = 50
    ) -> Dict[str, Any]:
        """Recalibrate item parameters from response histories using empirical logit estimation."""
        now = datetime.now(timezone.utc)

        # Query all active auto-gradable questions
        questions = (
            db.query(QuestionBank)
            .filter(
                QuestionBank.deleted_at.is_(None),
                QuestionBank.status == ContentStatus.ACTIVE,
                QuestionBank.question_type.in_(
                    [
                        QuestionType.MULTIPLE_CHOICE,
                        QuestionType.TRUE_FALSE_NOT_GIVEN,
                        QuestionType.YES_NO_NOT_GIVEN,
                    ]
                ),
            )
            .all()
        )

        calibrated_count = 0

        for q in questions:
            # Check test_responses + adaptive_quiz_responses
            resp_stats = db.execute(
                text(
                    """
                    SELECT 
                        (COALESCE(tr_total, 0) + COALESCE(ar_total, 0)) as total,
                        (COALESCE(tr_correct, 0) + COALESCE(ar_correct, 0)) as correct
                    FROM (
                        SELECT 
                            (SELECT count(*) FROM test_responses WHERE question_id = :qid) as tr_total,
                            (SELECT count(*) FROM test_responses WHERE question_id = :qid AND is_correct = true) as tr_correct,
                            (SELECT count(*) FROM adaptive_quiz_responses WHERE question_id = :qid) as ar_total,
                            (SELECT count(*) FROM adaptive_quiz_responses WHERE question_id = :qid AND is_correct = true) as ar_correct
                    ) s
                """
                ),
                {"qid": str(q.id)},
            ).fetchone()

            total = resp_stats[0] if resp_stats else 0
            correct = resp_stats[1] if resp_stats else 0

            if total >= min_responses:
                p_emp = max(0.05, min(0.95, correct / total))
                b_val = round(-math.log(p_emp / (1.0 - p_emp)), 4)
                a_val = round(1.0 + 0.5 * (1.0 - 4.0 * ((p_emp - 0.5) ** 2)), 4)
                c_val = 0.25 if q.question_type == QuestionType.MULTIPLE_CHOICE else 0.3333

                q.irt_discrimination = a_val
                q.irt_difficulty = b_val
                q.irt_guessing = c_val
                q.irt_calibrated = True
                q.irt_calibrated_at = now
                q.is_cat_eligible = True
                calibrated_count += 1

        db.commit()

        return {
            "calibrated_items_count": calibrated_count,
            "message": f"Hiệu chỉnh thành công {calibrated_count} câu hỏi thỏa mãn điều kiện >= {min_responses} lượt trả lời",
            "timestamp": now,
        }
