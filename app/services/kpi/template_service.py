"""
KPI Template Service — CRUD operations for KPI template configurations.
"""

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from uuid import UUID
from fastapi import HTTPException, status
from decimal import Decimal
import logging

from app.models.kpi import KPITemplate, KPITemplateMetric
from app.schemas.kpi import (
    KPITemplateCreate, KPITemplateUpdate,
    KPITemplateMetricCreate, KPITemplateMetricUpdate,
)

logger = logging.getLogger(__name__)


class KPITemplateService:

    def list_templates(self, db: Session) -> List[KPITemplate]:
        return db.query(KPITemplate).order_by(KPITemplate.created_at.desc()).all()

    def get_template(self, db: Session, template_id: UUID) -> KPITemplate:
        template = db.query(KPITemplate).filter(KPITemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Không tìm thấy template KPI")
        return template

    def create_template(self, db: Session, payload: KPITemplateCreate, created_by: UUID) -> KPITemplate:
        template = KPITemplate(
            name=payload.name,
            contract_type=payload.contract_type,
            max_bonus_amount=payload.max_bonus_amount,
            bonus_type=payload.bonus_type,
            effective_from=payload.effective_from,
            description=payload.description,
            version=1,
            is_active=True,
            created_by=created_by,
        )
        db.add(template)
        db.flush()  # Get the template.id

        # Add metrics
        for idx, m in enumerate(payload.metrics):
            metric = KPITemplateMetric(
                template_id=template.id,
                metric_code=m.metric_code,
                metric_name=m.metric_name,
                is_group_header=m.is_group_header,
                unit=m.unit,
                target_min=m.target_min,
                target_max=m.target_max,
                weight=m.weight,
                group_weight=m.group_weight,
                sort_order=m.sort_order if m.sort_order else idx,
                description=m.description,
            )
            db.add(metric)

        db.commit()
        db.refresh(template)
        return template

    def update_template(
        self, db: Session, template_id: UUID, payload: KPITemplateUpdate
    ) -> KPITemplate:
        """
        Update template metadata and/or metrics.
        Bumps version when metrics change.
        """
        template = self.get_template(db, template_id)

        # Update metadata fields
        if payload.name is not None:
            template.name = payload.name
        if payload.max_bonus_amount is not None:
            template.max_bonus_amount = payload.max_bonus_amount
        if payload.bonus_type is not None:
            template.bonus_type = payload.bonus_type
        if payload.effective_from is not None:
            template.effective_from = payload.effective_from
        if payload.description is not None:
            template.description = payload.description
        if payload.is_active is not None:
            template.is_active = payload.is_active

        # Update metrics if provided
        if payload.metrics is not None:
            # Validate weight sum
            metric_weights = [
                m.weight for m in payload.metrics
                if not m.is_group_header and m.weight is not None
            ]
            if metric_weights:
                total = sum(metric_weights)
                if not (0.99 <= total <= 1.01):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Tổng trọng số các tiêu chí phải bằng 1.0 (hiện tại: {total:.4f})"
                    )

            # Bump version
            template.version += 1

            # Get existing metric IDs
            existing_ids = {m.id for m in template.metrics}
            payload_ids = {m.id for m in payload.metrics if m.id is not None}

            # Delete removed metrics
            for metric in template.metrics:
                if metric.id not in payload_ids:
                    db.delete(metric)

            # Update or create metrics
            for idx, m_data in enumerate(payload.metrics):
                if m_data.id and m_data.id in existing_ids:
                    metric = db.query(KPITemplateMetric).filter(
                        KPITemplateMetric.id == m_data.id
                    ).first()
                    if metric:
                        metric.metric_code = m_data.metric_code
                        metric.metric_name = m_data.metric_name
                        metric.is_group_header = m_data.is_group_header
                        metric.unit = m_data.unit
                        metric.target_min = m_data.target_min
                        metric.target_max = m_data.target_max
                        metric.weight = m_data.weight
                        metric.group_weight = m_data.group_weight
                        metric.sort_order = m_data.sort_order if m_data.sort_order else idx
                        metric.description = m_data.description
                else:
                    new_metric = KPITemplateMetric(
                        template_id=template.id,
                        metric_code=m_data.metric_code,
                        metric_name=m_data.metric_name,
                        is_group_header=m_data.is_group_header,
                        unit=m_data.unit,
                        target_min=m_data.target_min,
                        target_max=m_data.target_max,
                        weight=m_data.weight,
                        group_weight=m_data.group_weight,
                        sort_order=m_data.sort_order if m_data.sort_order else idx,
                        description=m_data.description,
                    )
                    db.add(new_metric)

        db.commit()
        db.refresh(template)
        return template

    def get_metrics(self, db: Session, template_id: UUID) -> List[KPITemplateMetric]:
        template = self.get_template(db, template_id)
        return template.metrics


kpi_template_service = KPITemplateService()
