"""add_class_post_comments_and_reactions

Revision ID: 416cf8830c56
Revises: d11695e6b9fd
Create Date: 2026-09-14 15:33:02.768846

Phase 2: Thêm 2 bảng mới:
  - class_post_comments: Bình luận Q&A lồng 1 cấp trên bài viết lớp học
  - class_post_reactions: Toggle reaction (Like/Heart/Understood) trên bài viết
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '416cf8830c56'
down_revision: Union[str, None] = 'd11695e6b9fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── Bảng class_post_comments ─────────────────────────────────────────────
    op.create_table(
        'class_post_comments',
        sa.Column('post_id', sa.UUID(), nullable=False),
        sa.Column('author_id', sa.UUID(), nullable=False),
        sa.Column('parent_comment_id', sa.UUID(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_edited', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['parent_comment_id'], ['class_post_comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['post_id'], ['class_posts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_class_post_comments_author_id'), 'class_post_comments', ['author_id'], unique=False)
    op.create_index(op.f('ix_class_post_comments_parent_comment_id'), 'class_post_comments', ['parent_comment_id'], unique=False)
    op.create_index(op.f('ix_class_post_comments_post_id'), 'class_post_comments', ['post_id'], unique=False)
    # Partial index: active comments only, ordered by time
    op.create_index(
        'idx_comments_active',
        'class_post_comments',
        ['post_id', 'created_at'],
        unique=False,
        postgresql_where='deleted_at IS NULL',
    )

    # ─── Bảng class_post_reactions ────────────────────────────────────────────
    op.create_table(
        'class_post_reactions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('post_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('reaction_type', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['class_posts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('post_id', 'user_id', 'reaction_type', name='uq_reaction_post_user_type'),
    )
    op.create_index(op.f('ix_class_post_reactions_post_id'), 'class_post_reactions', ['post_id'], unique=False)
    op.create_index(op.f('ix_class_post_reactions_user_id'), 'class_post_reactions', ['user_id'], unique=False)


def downgrade() -> None:
    # ─── Drop class_post_reactions ────────────────────────────────────────────
    op.drop_index(op.f('ix_class_post_reactions_user_id'), table_name='class_post_reactions')
    op.drop_index(op.f('ix_class_post_reactions_post_id'), table_name='class_post_reactions')
    op.drop_table('class_post_reactions')

    # ─── Drop class_post_comments ─────────────────────────────────────────────
    op.drop_index('idx_comments_active', table_name='class_post_comments')
    op.drop_index(op.f('ix_class_post_comments_post_id'), table_name='class_post_comments')
    op.drop_index(op.f('ix_class_post_comments_parent_comment_id'), table_name='class_post_comments')
    op.drop_index(op.f('ix_class_post_comments_author_id'), table_name='class_post_comments')
    op.drop_table('class_post_comments')
