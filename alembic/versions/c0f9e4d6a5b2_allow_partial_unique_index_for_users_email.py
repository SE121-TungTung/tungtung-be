"""Allow users to reuse email when previous record is soft-deleted

Revision ID: c0f9e4d6a5b2
Revises: 08271459c983
Create Date: 2025-12-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c0f9e4d6a5b2'
down_revision = '08271459c983'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the existing unique index/constraint on users.email and create a
    # partial (filtered) unique index that enforces uniqueness only for
    # non-deleted rows (deleted_at IS NULL).

    # Drop older unique index if it exists
    try:
        op.drop_index('ix_users_email', table_name='users')
    except Exception:
        # ignore if missing
        pass

    # Drop unique constraint if it exists (some DBs have users_email_key)
    # Use raw SQL to be robust about constraint presence
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_email_key') THEN
                ALTER TABLE users DROP CONSTRAINT users_email_key;
            END IF;
        END$$;
        """
    )

    # Create partial unique index
    op.create_index(
        'uq_users_email_not_deleted',
        'users',
        ['email'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL')
    )


def downgrade() -> None:
    # Revert: drop the partial unique index and recreate former unique index/constraint
    try:
        op.drop_index('uq_users_email_not_deleted', table_name='users')
    except Exception:
        pass

    # Recreate a non-partial unique index to restore previous behavior
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # Optionally recreate the named unique constraint
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'users_email_key') THEN
                ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email);
            END IF;
        END$$;
        """
    )