"""Merge branch heads: 9d4dc8e7a84a and c0f9e4d6a5b2

Revision ID: d3f4a2b7c1e2
Revises: 9d4dc8e7a84a, c0f9e4d6a5b2
Create Date: 2025-12-26 00:00:00.000000
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd3f4a2b7c1e2'
down_revision = ('9d4dc8e7a84a', 'c0f9e4d6a5b2')
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge migration: no schema changes needed; this revision merges two heads.
    pass


def downgrade() -> None:
    # Downgrade would split the merge which is usually not needed; keep no-op.
    pass
