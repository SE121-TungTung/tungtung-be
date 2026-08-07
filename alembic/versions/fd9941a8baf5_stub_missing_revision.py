"""stub_for_missing_revision_fd9941a8baf5

Revision ID: fd9941a8baf5
Revises: 4f97900b9aeb
Create Date: 2026-08-06 22:20:00.000000

NOTE: Đây là stub file để khôi phục trạng thái alembic.
Revision fd9941a8baf5 đã được apply vào DB nhưng file migration bị mất.
Nội dung upgrade/downgrade trống vì bảng đã tồn tại trong DB.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fd9941a8baf5'
down_revision = '4f97900b9aeb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stub: migration này đã được apply vào DB.
    # Nội dung thực tế không còn được reconstruct.
    pass


def downgrade() -> None:
    # Stub: không rollback vì không biết nội dung gốc.
    pass
