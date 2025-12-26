"""Update test models - add question_groups safely

Revision ID: 5fc00f03d124
Revises: d3f4a2b7c1e2
Create Date: 2025-12-26 23:38:08.650988
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "5fc00f03d124"
down_revision: Union[str, None] = "d3f4a2b7c1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =====================================================
    # 1. CREATE question_groups
    # =====================================================
    op.create_table(
        "question_groups",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("part_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("instruction", sa.Text()),
        sa.Column("image_url", sa.String()),
        sa.Column("order_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.UUID()),
        sa.Column("updated_by", sa.UUID()),
        sa.ForeignKeyConstraint(["part_id"], ["test_section_parts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
    )

    # =====================================================
    # 2. ADD group_id (NULLABLE) to test_questions
    # =====================================================
    op.add_column(
        "test_questions",
        sa.Column("group_id", sa.UUID(), nullable=True),
    )

    # =====================================================
    # 3. BACKFILL DATA
    #    - mỗi part → 1 default question_group
    #    - gán toàn bộ question vào group đó
    # =====================================================
    op.execute(
        """
        INSERT INTO question_groups (
            id,
            part_id,
            title,
            order_number,
            created_at
        )
        SELECT
            gen_random_uuid(),
            tq.part_id,
            'Default Group',
            1,
            now()
        FROM test_questions tq
        GROUP BY tq.part_id;
        """
    )

    op.execute(
        """
        UPDATE test_questions tq
        SET group_id = qg.id
        FROM question_groups qg
        WHERE tq.part_id = qg.part_id;
        """
    )

    # =====================================================
    # 4. SET group_id NOT NULL + FK
    # =====================================================
    op.alter_column("test_questions", "group_id", nullable=False)

    op.create_foreign_key(
        "fk_test_questions_group",
        "test_questions",
        "question_groups",
        ["group_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # =====================================================
    # 5. DROP old part_id from test_questions
    # =====================================================
    op.drop_constraint(
        "test_questions_part_id_fkey",
        "test_questions",
        type_="foreignkey",
    )
    op.drop_column("test_questions", "part_id")

    # =====================================================
    # 6. OTHER SMALL CHANGES
    # =====================================================
    op.add_column(
        "test_section_parts",
        sa.Column("content", sa.Text()),
    )

    op.alter_column(
        "test_sections",
        "skill_area",
        existing_type=postgresql.ENUM(
            "listening",
            "reading",
            "writing",
            "speaking",
            "grammar",
            "vocabulary",
            "pronunciation",
            name="skill_area",
        ),
        nullable=False,
    )

    op.drop_index("idx_notifications_user", table_name="notifications")
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)


def downgrade() -> None:
    # =====================================================
    # REVERT OPTIONAL (basic)
    # =====================================================
    op.drop_index(op.f("ix_users_email"), table_name="users")

    op.alter_column(
        "test_sections",
        "skill_area",
        existing_type=postgresql.ENUM(
            "listening",
            "reading",
            "writing",
            "speaking",
            "grammar",
            "vocabulary",
            "pronunciation",
            name="skill_area",
        ),
        nullable=True,
    )

    op.drop_column("test_section_parts", "content")

    op.add_column(
        "test_questions",
        sa.Column("part_id", sa.UUID(), nullable=True),
    )

    op.create_foreign_key(
        "test_questions_part_id_fkey",
        "test_questions",
        "test_section_parts",
        ["part_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("fk_test_questions_group", "test_questions", type_="foreignkey")
    op.drop_column("test_questions", "group_id")

    op.create_index("idx_notifications_user", "notifications", ["user_id"])

    op.drop_table("question_groups")
