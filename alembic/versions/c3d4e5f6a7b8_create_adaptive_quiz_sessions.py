"""create_adaptive_quiz_sessions

Revision ID: c3d4e5f6a7b8
Revises: c2b3d4e5f6a7
Create Date: 2026-10-12 16:32:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'c2b3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'adaptive_quiz_sessions',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('skill_area', sa.String(length=20), nullable=False),
        sa.Column('theta_initial', sa.Numeric(7, 4), server_default='0.0000', nullable=False),
        sa.Column('theta_current', sa.Numeric(7, 4), nullable=False),
        sa.Column('theta_final', sa.Numeric(7, 4), nullable=True),
        sa.Column('se_current', sa.Numeric(6, 4), nullable=False),
        sa.Column('se_final', sa.Numeric(6, 4), nullable=True),
        sa.Column('items_administered', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_items', sa.Integer(), server_default='20', nullable=False),
        sa.Column('stop_reason', sa.String(length=30), nullable=True),
        sa.Column('estimated_band', sa.Numeric(3, 1), nullable=True),
        sa.Column('theta_history', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='in_progress', nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        # Audit fields from BaseModel
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('idx_adaptive_session_user_skill', 'adaptive_quiz_sessions', ['user_id', 'skill_area', 'status'])
    op.create_index('idx_adaptive_session_user_id', 'adaptive_quiz_sessions', ['user_id'])


def downgrade() -> None:
    op.drop_index('idx_adaptive_session_user_id', table_name='adaptive_quiz_sessions')
    op.drop_index('idx_adaptive_session_user_skill', table_name='adaptive_quiz_sessions')
    op.drop_table('adaptive_quiz_sessions')
