"""Merge branch heads: b4c5d6e7f8a9 and fc4d1e2f3a4b

Revision ID: c1a2b3d4e5f6
Revises: b4c5d6e7f8a9, fc4d1e2f3a4b
Create Date: 2026-10-12 16:20:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, Sequence[str], None] = ('b4c5d6e7f8a9', 'fc4d1e2f3a4b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
