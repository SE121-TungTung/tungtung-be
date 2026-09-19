"""add_lead_and_guest_session

Revision ID: f2b3c4d5e6f7
Revises: a9b2c1d4e8f0
Create Date: 2026-09-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f2b3c4d5e6f7'
down_revision: Union[str, None] = 'a9b2c1d4e8f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create leads table
    op.create_table('leads',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('guest_session_id', sa.String(length=255), nullable=True),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('status', sa.Enum('new', 'contacted', 'converted', 'lost', name='lead_status'), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_leads_email'), 'leads', ['email'], unique=False)
    op.create_index(op.f('ix_leads_phone'), 'leads', ['phone'], unique=False)
    op.create_index(op.f('ix_leads_guest_session_id'), 'leads', ['guest_session_id'], unique=False)

    # 2. Update test_attempts
    op.add_column('test_attempts', sa.Column('guest_session_id', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_test_attempts_guest_session_id'), 'test_attempts', ['guest_session_id'], unique=False)
    op.alter_column('test_attempts', 'student_id', existing_type=postgresql.UUID(as_uuid=True), nullable=True)


def downgrade() -> None:
    # 1. Revert test_attempts
    op.alter_column('test_attempts', 'student_id', existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_index(op.f('ix_test_attempts_guest_session_id'), table_name='test_attempts')
    op.drop_column('test_attempts', 'guest_session_id')

    # 2. Drop leads table
    op.drop_index(op.f('ix_leads_guest_session_id'), table_name='leads')
    op.drop_index(op.f('ix_leads_phone'), table_name='leads')
    op.drop_index(op.f('ix_leads_email'), table_name='leads')
    op.drop_table('leads')
    op.execute('DROP TYPE lead_status;')
