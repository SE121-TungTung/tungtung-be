"""create_pronunciation_word_list_items

Revision ID: d1e2f3a4b5c6
Revises: c4e5f6a7b8c9
Create Date: 2026-10-15 14:30:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'pronunciation_word_list_items',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('target_text', sa.String(500), nullable=False),
        sa.Column('text_key', sa.String(500), nullable=False),
        sa.Column('target_type', sa.String(20), nullable=False, server_default='word'),
        sa.Column('ipa', sa.String(200), nullable=True),
        sa.Column('source', sa.String(20), nullable=False, server_default='manual'),
        sa.Column('flashcard_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['flashcard_id'], ['flashcards.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_pron_word_list_student', 'pronunciation_word_list_items', ['student_id'])
    op.create_index(
        'uq_pron_word_list_student_text',
        'pronunciation_word_list_items',
        ['student_id', 'text_key'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_pron_word_list_student_text', table_name='pronunciation_word_list_items')
    op.drop_index('idx_pron_word_list_student', table_name='pronunciation_word_list_items')
    op.drop_table('pronunciation_word_list_items')
