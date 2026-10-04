"""add_pronunciation_mastery_and_assessments

Revision ID: b4c5d6e7f8a9
Revises: a9f5d301be5a
Create Date: 2026-09-29 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'a9f5d301be5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── pronunciation_phoneme_mastery ──────────────────────────
    op.create_table(
        'pronunciation_phoneme_mastery',
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('phoneme', sa.String(length=10), nullable=False),
        sa.Column('mastery_level', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('repetition_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('easiness_factor', sa.Numeric(precision=4, scale=2), nullable=False, server_default='2.5'),
        sa.Column('interval_days', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('next_review_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('total_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correct_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('avg_score_7d', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('last_practiced_at', sa.DateTime(timezone=True), nullable=True),
        # BaseModel / AuditMixin columns
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'phoneme', name='uq_phoneme_mastery_student_phoneme'),
        sa.CheckConstraint('mastery_level BETWEEN 0 AND 4', name='ck_mastery_level_range'),
    )
    op.create_index('idx_phoneme_mastery_student', 'pronunciation_phoneme_mastery', ['student_id'], unique=False)
    op.create_index('idx_phoneme_mastery_next_review', 'pronunciation_phoneme_mastery', ['student_id', 'next_review_at'], unique=False)

    # ── pronunciation_assessments ──────────────────────────────
    op.create_table(
        'pronunciation_assessments',
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('cefr_level', sa.String(length=5), nullable=True),
        sa.Column('ielts_band_estimate', sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column('weak_phonemes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('strong_phonemes', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('assessment_items', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('retake_count', sa.Integer(), nullable=False, server_default='0'),
        # BaseModel / AuditMixin columns
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_assessments_student_created', 'pronunciation_assessments', ['student_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_assessments_student_created', table_name='pronunciation_assessments')
    op.drop_table('pronunciation_assessments')

    op.drop_index('idx_phoneme_mastery_next_review', table_name='pronunciation_phoneme_mastery')
    op.drop_index('idx_phoneme_mastery_student', table_name='pronunciation_phoneme_mastery')
    op.drop_table('pronunciation_phoneme_mastery')
