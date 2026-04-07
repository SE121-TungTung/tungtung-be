from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
from uuid import UUID
from fastapi import HTTPException, status
from decimal import Decimal
import logging

from app.core.exceptions import APIException
from app.models.kpi import KpiTier, KpiCriteria, TeacherMonthlyKpi
from app.schemas.kpi import KpiTierUpdate

logger = logging.getLogger(__name__)

class KpiSettingsService:
    def get_all_tiers(self, db: Session) -> List[KpiTier]:
        return db.query(KpiTier).order_by(KpiTier.min_score.asc()).all()

    def bulk_update_tiers(self, db: Session, tiers_payload: List[KpiTierUpdate]) -> List[KpiTier]:
        if not tiers_payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dữ liệu cấu hình trống",
            )

        sorted_tiers = sorted(tiers_payload, key=lambda x: x.min_score)

        if sorted_tiers[0].min_score != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bậc đầu tiên phải có min_score = 0",
            )
        if sorted_tiers[-1].max_score != 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bậc cuối cùng phải có max_score = 100",
            )

        for i, current in enumerate(sorted_tiers):
            if current.min_score >= current.max_score:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Bậc '{current.tier_name}': min_score phải nhỏ hơn max_score",
                )

            if i < len(sorted_tiers) - 1:
                next_tier = sorted_tiers[i + 1]
                if current.max_score > next_tier.min_score:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Chồng chéo điểm giữa bậc '{current.tier_name}' "
                            f"và '{next_tier.tier_name}'"
                        ),
                    )
                if current.max_score < next_tier.min_score:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Khoảng trống điểm giữa bậc '{current.tier_name}' "
                            f"và '{next_tier.tier_name}'"
                        ),
                    )
        existing_ids = {t.id for t in db.query(KpiTier.id).all()}
        payload_ids  = {t.id for t in sorted_tiers if t.id is not None}
        ids_to_delete = existing_ids - payload_ids

        # Check FK trước khi xóa
        for del_id in ids_to_delete:
            in_use = db.query(TeacherMonthlyKpi).filter(
                TeacherMonthlyKpi.kpi_tier_id == del_id
            ).first()
            if in_use:
                raise HTTPException(
                    status_code=409,
                    detail=f"Bậc KPI (ID={del_id}) đang được sử dụng, không thể xóa"
                )

        try:
            # Cập nhật hoặc Thêm mới
            new_tiers = []
            for tier_data in sorted_tiers:
                data_dict = tier_data.model_dump(exclude={"id"})
                if tier_data.id and tier_data.id in existing_ids:
                    db.query(KpiTier).filter(KpiTier.id == tier_data.id).update(data_dict)
                else:
                    new_tier = KpiTier(**data_dict)
                    db.add(new_tier)
                    new_tiers.append(new_tier)

            # Xóa các id không còn trong cấu hình
            for del_id in ids_to_delete:
                db.query(KpiTier).filter(KpiTier.id == del_id).delete()

            db.commit()
            return db.query(KpiTier).order_by(KpiTier.min_score.asc()).all()
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"bulk_update_tiers failed: {e}", exc_info=True)
            raise APIException(
                status_code=500,
                code="INTERNAL_SERVER_ERROR",
                message="Đã có lỗi xảy ra khi cập nhật cấu hình bậc KPI",
            )


class KpiCriteriaService:
    def validate_total_weight(self, criteria_list) -> None:
        total = sum(Decimal(str(c.weight_percent)) for c in criteria_list)
        if total != Decimal("100"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tổng trọng số tiêu chí KPI phải bằng 100%. Hiện tại: {total}%",
            )

kpi_settings_service = KpiSettingsService()
kpi_criteria_service = KpiCriteriaService()
