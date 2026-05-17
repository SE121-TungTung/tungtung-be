"""Add online fields to class

Revision ID: 4f97900b9aeb
Revises: 20e1c3ee38e0
Create Date: 2026-05-17 13:00:59.303602

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f97900b9aeb'
down_revision: Union[str, None] = '20e1c3ee38e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('classes', sa.Column('is_online', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('classes', sa.Column('online_meeting_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('classes', 'online_meeting_url')
    op.drop_column('classes', 'is_online')
