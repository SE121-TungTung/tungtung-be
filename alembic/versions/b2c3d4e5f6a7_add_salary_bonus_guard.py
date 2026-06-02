"""add salary bonus guard column

Revision ID: b2c3d4e5f6a7
Revises: a7b8c9d0e1f2
Create Date: 2026-04-27

Add bonus_from_kpi_period_id to salaries table to track which KPI period
the bonus was sourced from, preventing duplicate bonus across months.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('salaries',
        sa.Column('bonus_from_kpi_period_id', UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_salaries_kpi_period',
        'salaries', 'kpi_periods',
        ['bonus_from_kpi_period_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_salaries_kpi_period', 'salaries', type_='foreignkey')
    op.drop_column('salaries', 'bonus_from_kpi_period_id')
