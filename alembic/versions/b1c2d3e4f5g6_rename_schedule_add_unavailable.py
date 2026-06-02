"""Rename schedule to preferred_slots and add unavailable_slots

Revision ID: b1c2d3e4f5g6
Revises: a7b8c9d0e1f2
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = 'b1c2d3e4f5g6'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Rename schedule → preferred_slots
    op.alter_column('classes', 'schedule', new_column_name='preferred_slots')
    # 2. Add unavailable_slots column
    op.add_column('classes', sa.Column(
        'unavailable_slots', JSONB, nullable=False, server_default='[]'
    ))


def downgrade():
    op.drop_column('classes', 'unavailable_slots')
    op.alter_column('classes', 'preferred_slots', new_column_name='schedule')
