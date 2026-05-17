"""Add certificates table

Revision ID: 20e1c3ee38e0
Revises: a75cc26827b8
Create Date: 2026-05-17 12:59:36.650535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20e1c3ee38e0'
down_revision: Union[str, None] = 'a75cc26827b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'certificates',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('course_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('class_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('certificate_code', sa.String(length=50), nullable=False),
        sa.Column('issue_date', sa.Date(), nullable=False),
        sa.Column('certificate_url', sa.Text(), nullable=True),
        sa.Column('final_score', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('attendance_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', sa.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(['class_id'], ['classes.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_certificates_certificate_code'), 'certificates', ['certificate_code'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_certificates_certificate_code'), table_name='certificates')
    op.drop_table('certificates')
