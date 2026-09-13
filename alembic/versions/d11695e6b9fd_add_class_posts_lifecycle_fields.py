"""add_class_posts_lifecycle_fields

Revision ID: d11695e6b9fd
Revises: fd9941a8baf5
Create Date: 2026-09-13

Bổ sung các cột vòng đời bài viết lớp học:
  - material_category  : Phân loại tài liệu (lecture_slide, exercise, ...)
  - is_pinned          : Cờ ghim bài (max 3 bài / lớp)
  - pinned_at          : Thời điểm ghim
  - is_comment_locked  : Khoá bình luận
  - is_edited          : Đã từng chỉnh sửa
  - deleted_by         : FK → users.id (ai đã soft-delete bài này)

Tạo 2 partial indexes tối ưu hoá query:
  1. idx_class_posts_active  : Danh sách bài active (deleted_at IS NULL)
  2. idx_class_posts_pinned  : Danh sách bài ghim active
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = 'd11695e6b9fd'
down_revision = 'fd9941a8baf5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── Thêm cột material_category ────────────────────────────────────────
    op.add_column(
        'class_posts',
        sa.Column(
            'material_category',
            sa.String(length=50),
            nullable=True,
            comment='Phân loại tài liệu: lecture_slide | exercise | reference | audio | video | other'
        )
    )

    # ─── Thêm cột is_pinned ─────────────────────────────────────────────────
    op.add_column(
        'class_posts',
        sa.Column(
            'is_pinned',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('FALSE'),
            comment='Bài viết có đang được ghim? (tối đa 3 bài/lớp)'
        )
    )

    # ─── Thêm cột pinned_at ─────────────────────────────────────────────────
    op.add_column(
        'class_posts',
        sa.Column(
            'pinned_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Thời điểm ghim bài'
        )
    )

    # ─── Thêm cột is_comment_locked ─────────────────────────────────────────
    op.add_column(
        'class_posts',
        sa.Column(
            'is_comment_locked',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('FALSE'),
            comment='Khoá bình luận trên bài viết'
        )
    )

    # ─── Thêm cột is_edited ─────────────────────────────────────────────────
    op.add_column(
        'class_posts',
        sa.Column(
            'is_edited',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('FALSE'),
            comment='Bài viết đã được chỉnh sửa ít nhất 1 lần'
        )
    )

    # ─── Thêm cột deleted_by ─────────────────────────────────────────────────
    op.add_column(
        'class_posts',
        sa.Column(
            'deleted_by',
            UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
            comment='ID người thực hiện soft-delete bài viết'
        )
    )

    # ─── Tạo index cho FK deleted_by ─────────────────────────────────────────
    op.create_index(
        'idx_class_posts_deleted_by',
        'class_posts',
        ['deleted_by'],
        unique=False,
    )

    # ─── Partial index 1: Query danh sách bài active (deleted_at IS NULL) ────
    # Hỗ trợ query: SELECT ... WHERE class_id = ? AND deleted_at IS NULL
    # ORDER BY is_pinned DESC, created_at DESC
    op.create_index(
        'idx_class_posts_active',
        'class_posts',
        ['class_id', 'is_pinned', 'created_at'],
        unique=False,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )

    # ─── Partial index 2: Query bài ghim active ──────────────────────────────
    # Hỗ trợ query: SELECT ... WHERE class_id = ? AND is_pinned = TRUE AND deleted_at IS NULL
    op.create_index(
        'idx_class_posts_pinned',
        'class_posts',
        ['class_id', 'pinned_at'],
        unique=False,
        postgresql_where=sa.text('is_pinned = TRUE AND deleted_at IS NULL'),
    )


def downgrade() -> None:
    # Xoá indexes
    op.drop_index('idx_class_posts_pinned',    table_name='class_posts')
    op.drop_index('idx_class_posts_active',    table_name='class_posts')
    op.drop_index('idx_class_posts_deleted_by', table_name='class_posts')

    # Xoá các cột đã thêm (theo thứ tự ngược)
    op.drop_column('class_posts', 'deleted_by')
    op.drop_column('class_posts', 'is_edited')
    op.drop_column('class_posts', 'is_comment_locked')
    op.drop_column('class_posts', 'pinned_at')
    op.drop_column('class_posts', 'is_pinned')
    op.drop_column('class_posts', 'material_category')
