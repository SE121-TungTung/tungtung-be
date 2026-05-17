"""Add substitution_requests table

Revision ID: a75cc26827b8
Revises: a1587f0e8f6c
Create Date: 2026-05-17 12:47:20.259471

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a75cc26827b8'
down_revision: Union[str, None] = 'a1587f0e8f6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 3. Create substitution_requests table
    substitution_status = sa.Enum('PENDING', 'ACCEPTED', 'DECLINED', 'APPROVED', 'REJECTED', 'CANCELLED', name='substitution_status', create_type=False)
    op.create_table(
        'substitution_requests',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('class_session_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('requesting_teacher_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('target_substitute_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', substitution_status, nullable=False),
        sa.Column('admin_approval_required', sa.Boolean(), nullable=True, default=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('admin_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', sa.UUID(as_uuid=True), nullable=True),
        
        sa.ForeignKeyConstraint(['class_session_id'], ['class_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['requesting_teacher_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_substitute_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('substitution_requests')
    # Note: Enum type might be kept or dropped, dropping enum is safer using raw SQL
    op.execute('DROP TYPE IF EXISTS substitution_status')
