"""add_pronunciation_practices_table

Revision ID: a9f5d301be5a
Revises: db547f644f41
Create Date: 2026-09-23 22:20:47.441412

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a9f5d301be5a'
down_revision: Union[str, None] = 'db547f644f41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pronunciation_practices',
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('target_text', sa.String(length=500), nullable=False),
        sa.Column(
            'target_type',
            sa.Enum('word', 'phrase', 'sentence', 'ipa', name='pronunciation_target_type', native_enum=False),
            nullable=False
        ),
        sa.Column('target_ipa', sa.String(length=500), nullable=True),
        sa.Column('actual_ipa', sa.String(length=500), nullable=True),
        sa.Column('audio_url', sa.Text(), nullable=True),
        sa.Column('overall_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('phoneme_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('component_scores', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('feedback_text', sa.Text(), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_pronunciation_practices_student_id', 'pronunciation_practices', ['student_id'], unique=False)
    op.create_index('idx_pronunciation_practices_student_created', 'pronunciation_practices', ['student_id', 'created_at'], unique=False)
    op.create_index('idx_pronunciation_practices_student_target_type', 'pronunciation_practices', ['student_id', 'target_type'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_pronunciation_practices_student_target_type', table_name='pronunciation_practices')
    op.drop_index('idx_pronunciation_practices_student_created', table_name='pronunciation_practices')
    op.drop_index('idx_pronunciation_practices_student_id', table_name='pronunciation_practices')
    op.drop_table('pronunciation_practices')
