"""drop deprecated kpi tables

Revision ID: a7b8c9d0e1f2
Revises: e9f93078cf92
Create Date: 2026-04-27

Drop deprecated KPI tables that have been superseded by the Lotus KPI system:
- kpi_calculation_jobs
- kpi_criterias
- kpi_raw_metrics
- teacher_monthly_kpis
- kpi_tiers
Also drops kpi_disputes.kpi_id column (old FK to teacher_monthly_kpis).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'e9f93078cf92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop FK constraint and column kpi_disputes.kpi_id
    op.drop_constraint('kpi_disputes_kpi_id_fkey', 'kpi_disputes', type_='foreignkey')
    op.drop_column('kpi_disputes', 'kpi_id')

    # 2. Drop tables in dependency order
    # teacher_monthly_kpis depends on kpi_tiers (FK kpi_tier_id)
    op.drop_table('teacher_monthly_kpis')
    op.drop_table('kpi_tiers')
    op.drop_table('kpi_calculation_jobs')
    op.drop_table('kpi_criterias')
    op.drop_table('kpi_raw_metrics')

    # 3. Drop orphaned enum types (safe — only used by dropped tables)
    op.execute("DROP TYPE IF EXISTS kpi_tier_status_enum")
    op.execute("DROP TYPE IF EXISTS kpi_criteria_status_enum")
    # Note: job_status_enum is still used by payroll_runs, so we keep it


def downgrade() -> None:
    # Recreate enum types
    op.execute("CREATE TYPE kpi_tier_status_enum AS ENUM ('ACTIVE', 'INACTIVE')")
    op.execute("CREATE TYPE kpi_criteria_status_enum AS ENUM ('ACTIVE', 'INACTIVE')")

    # Recreate tables in reverse dependency order
    op.create_table('kpi_tiers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tier_name', sa.String(length=20), nullable=False),
        sa.Column('min_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('max_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('reward_percentage', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('reward_per_lesson', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', name='kpi_tier_status_enum'), nullable=True),
        sa.CheckConstraint('max_score <= 100', name='check_max_score_limit'),
        sa.CheckConstraint('min_score < max_score', name='check_min_less_than_max'),
        sa.CheckConstraint('min_score >= 0', name='check_min_score_positive'),
        sa.CheckConstraint('reward_per_lesson >= 0', name='check_reward_per_lesson'),
        sa.CheckConstraint('reward_percentage >= 0', name='check_reward_positive'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tier_name')
    )

    op.create_table('teacher_monthly_kpis',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('teacher_id', sa.UUID(), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('total_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('kpi_tier_id', sa.Integer(), nullable=True),
        sa.Column('kpi_details', sa.JSON(), nullable=False),
        sa.Column('calculated_bonus', sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('finalized_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint('total_score >= 0 AND total_score <= 100', name='check_total_score'),
        sa.ForeignKeyConstraint(['kpi_tier_id'], ['kpi_tiers.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('teacher_id', 'period', name='uix_teacher_period')
    )

    op.create_table('kpi_calculation_jobs',
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', name='job_status_enum'), nullable=True),
        sa.Column('total_teachers', sa.Integer(), nullable=True),
        sa.Column('processed_count', sa.Integer(), nullable=True),
        sa.Column('error_log', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('job_id')
    )

    op.create_table('kpi_criterias',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('criteria_code', sa.String(length=50), nullable=False),
        sa.Column('criteria_name', sa.String(length=100), nullable=False),
        sa.Column('weight_percent', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('status', sa.Enum('ACTIVE', 'INACTIVE', name='kpi_criteria_status_enum'), nullable=True),
        sa.CheckConstraint('weight_percent > 0', name='check_weight_positive'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('criteria_code')
    )

    op.create_table('kpi_raw_metrics',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('teacher_id', sa.UUID(), nullable=False),
        sa.Column('period', sa.String(length=7), nullable=False),
        sa.Column('source_module', sa.String(length=50), nullable=False),
        sa.Column('metric_data', sa.JSON(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('teacher_id', 'period', 'source_module', name='uix_kpi_raw_sync')
    )

    # Re-add kpi_id column to kpi_disputes
    op.add_column('kpi_disputes',
        sa.Column('kpi_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        'kpi_disputes_kpi_id_fkey', 'kpi_disputes',
        'teacher_monthly_kpis', ['kpi_id'], ['id']
    )
