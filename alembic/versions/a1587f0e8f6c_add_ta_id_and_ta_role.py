"""add ta_id and TA role

Revision ID: a1587f0e8f6c
Revises: f042960a32f9
Create Date: 2026-05-17 12:41:52.193723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1587f0e8f6c'
down_revision: Union[str, None] = 'f042960a32f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add 'ta' to user_role enum
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'ta'")
        
    # 2. Add ta_id column to classes
    op.add_column('classes', sa.Column('ta_id', sa.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(None, 'classes', 'users', ['ta_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint(None, 'classes', type_='foreignkey')
    op.drop_column('classes', 'ta_id')
    # Note: Removing a value from a PostgreSQL enum is non-trivial and often unnecessary.
    # We leave the 'ta' value in the user_role enum.
