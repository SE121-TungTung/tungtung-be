"""create_adaptive_quiz_responses

Revision ID: c4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-12 16:34:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'adaptive_quiz_responses',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('question_id', sa.UUID(), nullable=False),
        sa.Column('item_position', sa.Integer(), nullable=False),
        sa.Column('theta_before', sa.Numeric(7, 4), nullable=False),
        sa.Column('theta_after', sa.Numeric(7, 4), nullable=False),
        sa.Column('se_before', sa.Numeric(6, 4), nullable=False),
        sa.Column('se_after', sa.Numeric(6, 4), nullable=False),
        sa.Column('fisher_info_at_selection', sa.Numeric(10, 6), nullable=True),
        sa.Column('irt_a_used', sa.Numeric(6, 4), nullable=False),
        sa.Column('irt_b_used', sa.Numeric(6, 4), nullable=False),
        sa.Column('irt_c_used', sa.Numeric(6, 4), nullable=False),
        sa.Column('response_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('is_correct', sa.Boolean(), nullable=False),
        sa.Column('time_spent_seconds', sa.Integer(), nullable=True),
        # Audit fields from BaseModel
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['adaptive_quiz_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['question_id'], ['question_bank.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'item_position', name='uq_adaptive_response_session_item')
    )

    op.create_index('idx_adaptive_response_session_id', 'adaptive_quiz_responses', ['session_id'])
    op.create_index('idx_adaptive_response_question_id', 'adaptive_quiz_responses', ['question_id'])


def downgrade() -> None:
    op.drop_index('idx_adaptive_response_question_id', table_name='adaptive_quiz_responses')
    op.drop_index('idx_adaptive_response_session_id', table_name='adaptive_quiz_responses')
    op.drop_table('adaptive_quiz_responses')
