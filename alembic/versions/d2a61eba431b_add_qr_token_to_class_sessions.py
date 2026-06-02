"""add_qr_token_to_class_sessions

Revision ID: d2a61eba431b
Revises: 762f0df642be
Create Date: 2026-04-11 16:20:12.276064

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd2a61eba431b'
down_revision: Union[str, None] = '762f0df642be'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add QR code columns to class_sessions for student self check-in
    op.add_column('class_sessions', sa.Column('qr_token', sa.String(length=64), nullable=True))
    op.add_column('class_sessions', sa.Column('qr_expires_at', sa.TIMESTAMP(timezone=True), nullable=True))
    op.create_index(op.f('ix_class_sessions_qr_token'), 'class_sessions', ['qr_token'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_class_sessions_qr_token'), table_name='class_sessions')
    op.drop_column('class_sessions', 'qr_expires_at')
    op.drop_column('class_sessions', 'qr_token')
