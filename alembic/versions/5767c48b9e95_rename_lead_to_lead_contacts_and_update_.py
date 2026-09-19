"""rename lead to lead_contacts and update columns

Revision ID: 5767c48b9e95
Revises: f2b3c4d5e6f7
Create Date: 2026-09-18 10:40:42.350028

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5767c48b9e95'
down_revision: Union[str, None] = 'f2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create lead_contacts table
    op.create_table('lead_contacts',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text('uuid_generate_v4()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('full_name', sa.String(length=200), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('guest_session_id', sa.String(length=255), nullable=True),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='new'),
        sa.Column('target_band', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_lead_contacts_email'), 'lead_contacts', ['email'], unique=False)
    op.create_index(op.f('ix_lead_contacts_phone'), 'lead_contacts', ['phone'], unique=False)
    op.create_index(op.f('ix_lead_contacts_guest_session_id'), 'lead_contacts', ['guest_session_id'], unique=False)

    # 2. Add guest_session_id to test_attempts if it doesn't exist
    op.add_column('test_attempts', sa.Column('guest_session_id', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_test_attempts_guest_session_id'), 'test_attempts', ['guest_session_id'], unique=False)
    op.alter_column('test_attempts', 'student_id', existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=True)


def downgrade() -> None:
    # 1. Revert test_attempts
    op.alter_column('test_attempts', 'student_id', existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=False)
    op.drop_index(op.f('ix_test_attempts_guest_session_id'), table_name='test_attempts')
    op.drop_column('test_attempts', 'guest_session_id')

    # 2. Drop lead_contacts table
    op.drop_index(op.f('ix_lead_contacts_guest_session_id'), table_name='lead_contacts')
    op.drop_index(op.f('ix_lead_contacts_phone'), table_name='lead_contacts')
    op.drop_index(op.f('ix_lead_contacts_email'), table_name='lead_contacts')
    op.drop_table('lead_contacts')
