"""refactor kpi tables

Revision ID: f1a2b3c4d5e6
Revises: d3f4a2b7c1e2
Create Date: 2026-04-22

New tables for the Lotus KPI template-based system:
- kpi_templates
- kpi_template_metrics
- kpi_periods
- kpi_records
- kpi_metric_results
- kpi_approval_logs
- support_calc_entries

Also adds kpi_record_id FK to kpi_disputes for migration.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = 'f1a2b3c4d5e6'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # KPI Templates
    op.create_table(
        'kpi_templates',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('contract_type', sa.String(50), nullable=False),
        sa.Column('max_bonus_amount', sa.Numeric(15, 2), nullable=False, server_default='0'),
        sa.Column('bonus_type', sa.String(50), server_default="'FIXED_PER_PERIOD'"),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('effective_from', sa.Date, nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('created_by', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )

    # KPI Template Metrics
    op.create_table(
        'kpi_template_metrics',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('template_id', UUID(as_uuid=True), sa.ForeignKey('kpi_templates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('metric_code', sa.String(10), nullable=False),
        sa.Column('metric_name', sa.String(255), nullable=False),
        sa.Column('is_group_header', sa.Boolean, server_default='false'),
        sa.Column('unit', sa.String(20), nullable=True),
        sa.Column('target_min', sa.Numeric(10, 4), nullable=True),
        sa.Column('target_max', sa.Numeric(10, 4), nullable=True),
        sa.Column('weight', sa.Numeric(5, 4), nullable=True),
        sa.Column('group_weight', sa.Numeric(5, 4), nullable=True),
        sa.Column('sort_order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('description', sa.Text, nullable=True),
        sa.UniqueConstraint('template_id', 'metric_code', name='uix_template_metric_code'),
    )

    # KPI Periods
    op.create_table(
        'kpi_periods',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('period_type', sa.String(20), server_default="'SEMESTER'"),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('end_date', sa.Date, nullable=False),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_by', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # KPI Records
    op.create_table(
        'kpi_records',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('staff_id', UUID(as_uuid=True), nullable=False),
        sa.Column('period_id', UUID(as_uuid=True), sa.ForeignKey('kpi_periods.id'), nullable=False),
        sa.Column('template_id', UUID(as_uuid=True), sa.ForeignKey('kpi_templates.id'), nullable=False),
        sa.Column('total_score', sa.Numeric(5, 4), nullable=True),
        sa.Column('bonus_amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('teaching_hours', sa.Numeric(8, 2), nullable=True),
        sa.Column('approval_status', sa.String(20), server_default="'DRAFT'"),
        sa.Column('submitted_at', sa.DateTime, nullable=True),
        sa.Column('approved_by', UUID(as_uuid=True), nullable=True),
        sa.Column('approved_at', sa.DateTime, nullable=True),
        sa.Column('rejection_note', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint('staff_id', 'period_id', name='uix_staff_period'),
    )

    # Support Calc Entries (must be created before kpi_metric_results due to FK)
    op.create_table(
        'support_calc_entries',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('kpi_record_id', UUID(as_uuid=True), sa.ForeignKey('kpi_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('class_name', sa.String(100), nullable=True),
        sa.Column('class_size', sa.Integer, nullable=False),
        sa.Column('max_score', sa.Numeric(5, 2), nullable=False),
        sa.Column('avg_threshold', sa.Numeric(5, 2), nullable=False),
        sa.Column('above_avg_count', sa.Integer, nullable=False),
        sa.Column('high_threshold', sa.Numeric(5, 2), nullable=False),
        sa.Column('above_high_count', sa.Integer, nullable=False),
        sa.Column('rate_above_avg', sa.Numeric(5, 4), nullable=False),
        sa.Column('rate_above_high', sa.Numeric(5, 4), nullable=False),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # KPI Metric Results
    op.create_table(
        'kpi_metric_results',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('kpi_record_id', UUID(as_uuid=True), sa.ForeignKey('kpi_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('metric_id', UUID(as_uuid=True), sa.ForeignKey('kpi_template_metrics.id'), nullable=False),
        sa.Column('actual_value', sa.Numeric(10, 4), nullable=True),
        sa.Column('converted_score', sa.Numeric(5, 4), nullable=True),
        sa.Column('data_source', sa.String(20), server_default="'MANUAL'"),
        sa.Column('support_calc_id', UUID(as_uuid=True), sa.ForeignKey('support_calc_entries.id'), nullable=True),
        sa.Column('note', sa.Text, nullable=True),
        sa.UniqueConstraint('kpi_record_id', 'metric_id', name='uix_record_metric'),
    )

    # KPI Approval Logs
    op.create_table(
        'kpi_approval_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('kpi_record_id', UUID(as_uuid=True), sa.ForeignKey('kpi_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('action', sa.String(30), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), nullable=False),
        sa.Column('comment', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )

    # Add kpi_record_id to kpi_disputes (migration from old kpi_id)
    op.add_column(
        'kpi_disputes',
        sa.Column('kpi_record_id', UUID(as_uuid=True), sa.ForeignKey('kpi_records.id'), nullable=True),
    )

    # Make old kpi_id nullable (was previously required)
    op.alter_column('kpi_disputes', 'kpi_id', nullable=True)


def downgrade() -> None:
    # Remove kpi_record_id from disputes
    op.drop_column('kpi_disputes', 'kpi_record_id')
    op.alter_column('kpi_disputes', 'kpi_id', nullable=False)

    # Drop new tables in reverse dependency order
    op.drop_table('kpi_approval_logs')
    op.drop_table('kpi_metric_results')
    op.drop_table('support_calc_entries')
    op.drop_table('kpi_records')
    op.drop_table('kpi_periods')
    op.drop_table('kpi_template_metrics')
    op.drop_table('kpi_templates')
