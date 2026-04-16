"""add_ga_schedule_tables

Revision ID: a1b2c3d4e5f6
Revises: d2a61eba431b
Create Date: 2026-04-16 00:37:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd2a61eba431b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type for GA run status
    ga_run_status = postgresql.ENUM(
        'pending', 'running', 'completed', 'failed', 'applied',
        name='ga_run_status',
        create_type=False
    )
    ga_run_status.create(op.get_bind(), checkfirst=True)

    # 1. ga_runs — GA execution tracking
    op.create_table('ga_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Enum(
            'pending', 'running', 'completed', 'failed', 'applied',
            name='ga_run_status', native_enum=True
        ), nullable=False, server_default='pending'),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('class_ids', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True),
        sa.Column('config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('best_fitness', sa.Float(), nullable=True),
        sa.Column('hard_violations', sa.Integer(), nullable=True),
        sa.Column('soft_score', sa.Float(), nullable=True),
        sa.Column('generations_run', sa.Integer(), nullable=True),
        sa.Column('result_summary', postgresql.JSONB(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        # Audit fields from BaseModel
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=True),
        sa.CheckConstraint('start_date <= end_date', name='ga_runs_date_range_check'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ga_runs_status', 'ga_runs', ['status'])

    # 2. ga_schedule_proposals — Session proposals from GA
    op.create_table('ga_schedule_proposals',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ga_run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('class_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('teacher_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('room_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_date', sa.Date(), nullable=False),
        sa.Column('time_slots', postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('lesson_topic', sa.String(255), nullable=True),
        sa.Column('is_conflict', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('conflict_details', postgresql.JSONB(), nullable=True),
        # Audit fields from BaseModel
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=True),
        sa.ForeignKeyConstraint(['ga_run_id'], ['ga_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ga_schedule_proposals_ga_run_id', 'ga_schedule_proposals', ['ga_run_id'])
    op.create_index('ix_ga_schedule_proposals_session_date', 'ga_schedule_proposals', ['session_date'])

    # 3. teacher_unavailability — Teacher time blocking constraints
    op.create_table('teacher_unavailability',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('teacher_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('unavailable_date', sa.Date(), nullable=True),
        sa.Column('time_slots', postgresql.ARRAY(sa.SmallInteger()), nullable=True),
        sa.Column('reason', sa.String(255), nullable=True),
        sa.Column('is_recurring', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('day_of_week', sa.SmallInteger(), nullable=True),
        # Audit fields from BaseModel
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('updated_by', sa.UUID(), sa.ForeignKey('users.id'), nullable=True),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], ondelete='CASCADE'),
        sa.CheckConstraint(
            '(is_recurring = false AND unavailable_date IS NOT NULL) OR '
            '(is_recurring = true AND day_of_week IS NOT NULL)',
            name='teacher_unavailability_date_or_recurring_check'
        ),
        sa.CheckConstraint(
            'day_of_week IS NULL OR (day_of_week >= 0 AND day_of_week <= 6)',
            name='teacher_unavailability_day_of_week_check'
        ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_teacher_unavailability_teacher_id', 'teacher_unavailability', ['teacher_id'])
    op.create_index('ix_teacher_unavailability_date', 'teacher_unavailability', ['unavailable_date'])


def downgrade() -> None:
    op.drop_table('teacher_unavailability')
    op.drop_table('ga_schedule_proposals')
    op.drop_table('ga_runs')

    # Drop enum type
    ga_run_status = postgresql.ENUM('pending', 'running', 'completed', 'failed', 'applied', name='ga_run_status')
    ga_run_status.drop(op.get_bind(), checkfirst=True)
