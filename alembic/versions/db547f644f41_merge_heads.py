"""merge heads 5767c48b9e95 and e91ba393d070

Revision ID: db547f644f41
Revises: 5767c48b9e95, e91ba393d070
Create Date: 2026-09-23 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db547f644f41'
down_revision: Union[str, Sequence[str], None] = ('5767c48b9e95', 'e91ba393d070')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
