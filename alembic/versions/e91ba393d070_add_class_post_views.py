"""add_class_post_views

Revision ID: e91ba393d070
Revises: 416cf8830c56
Create Date: 2026-09-14 17:15:12.914789

Phase 3: Thêm bảng class_post_views
  - Ghi nhận lượt xem (View Tracking) của học viên trên bài viết lớp học
  - Unique constraint (post_id, user_id) để đảm bảo tính idempotent
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e91ba393d070'
down_revision: Union[str, None] = '416cf8830c56'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'class_post_views',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('post_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('viewed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['class_posts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('post_id', 'user_id', name='uq_view_post_user'),
    )
    op.create_index(op.f('ix_class_post_views_post_id'), 'class_post_views', ['post_id'], unique=False)
    op.create_index(op.f('ix_class_post_views_user_id'), 'class_post_views', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_class_post_views_user_id'), table_name='class_post_views')
    op.drop_index(op.f('ix_class_post_views_post_id'), table_name='class_post_views')
    op.drop_table('class_post_views')
