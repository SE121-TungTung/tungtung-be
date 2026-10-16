"""pronunciation ipa us/uk + practice items

- dictionary_words: tạo nếu chưa có (bảng này trước đây chưa có migration), thêm ipa_us / ipa_uk
- pronunciation_practice_items: kho bài luyện do AI sinh, dùng chung

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-10-16 11:40:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_columns():
    return [
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # 1. dictionary_words
    if 'dictionary_words' not in tables:
        op.create_table(
            'dictionary_words',
            *_audit_columns(),
            sa.Column('word', sa.String(255), nullable=False),
            sa.Column('ipa', sa.String(255), nullable=True),
            sa.Column('ipa_us', sa.String(255), nullable=True),
            sa.Column('ipa_uk', sa.String(255), nullable=True),
            sa.Column('word_type', sa.String(50), nullable=True),
            sa.Column('definition_en', sa.Text(), nullable=True),
            sa.Column('example_sentence', sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(['created_by'], ['users.id']),
            sa.ForeignKeyConstraint(['updated_by'], ['users.id']),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_dictionary_words_word', 'dictionary_words', ['word'], unique=True)
    else:
        existing = {c['name'] for c in inspector.get_columns('dictionary_words')}
        if 'ipa_us' not in existing:
            op.add_column('dictionary_words', sa.Column('ipa_us', sa.String(255), nullable=True))
        if 'ipa_uk' not in existing:
            op.add_column('dictionary_words', sa.Column('ipa_uk', sa.String(255), nullable=True))

    # 2. pronunciation_practice_items
    op.create_table(
        'pronunciation_practice_items',
        *_audit_columns(),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('context_key', sa.String(120), nullable=False),
        sa.Column('text', sa.String(500), nullable=False),
        sa.Column('text_key', sa.String(500), nullable=False),
        sa.Column('target_type', sa.String(20), nullable=False, server_default='word'),
        sa.Column('ipa_us', sa.String(500), nullable=True),
        sa.Column('ipa_uk', sa.String(500), nullable=True),
        sa.Column('hint', sa.Text(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'idx_pron_practice_items_ctx', 'pronunciation_practice_items', ['kind', 'context_key']
    )
    op.create_index(
        'uq_pron_practice_items_ctx_text',
        'pronunciation_practice_items',
        ['kind', 'context_key', 'text_key'],
        unique=True,
        postgresql_where=sa.text('deleted_at IS NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_pron_practice_items_ctx_text', table_name='pronunciation_practice_items')
    op.drop_index('idx_pron_practice_items_ctx', table_name='pronunciation_practice_items')
    op.drop_table('pronunciation_practice_items')
    op.drop_column('dictionary_words', 'ipa_uk')
    op.drop_column('dictionary_words', 'ipa_us')
