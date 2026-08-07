"""add_user_vocabulary_table

Revision ID: a9b2c1d4e8f0
Revises: f042960a32f9
Create Date: 2026-08-06 21:53:00.000000

Spec ref: ielts_system_spec_part2.md § 3.2.3 Vocabulary & Collocation Notebook
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a9b2c1d4e8f0'
down_revision = 'fd9941a8baf5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_vocabulary',

        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),

        # Quan hệ user
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

        # Từ vựng
        sa.Column('word', sa.String(200), nullable=False),
        sa.Column('ipa', sa.String(200), nullable=True),
        sa.Column('meaning_vi', sa.Text(), nullable=True),
        sa.Column('example', sa.Text(), nullable=True),
        sa.Column('word_type', sa.String(50), nullable=True),

        # Nguồn
        sa.Column('source_passage_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('content_passages.id', ondelete='SET NULL'), nullable=True),

        # Tiến độ học
        sa.Column('mastery_level', sa.Integer(), nullable=False, server_default='0'),

        # Timestamps (từ BaseModel pattern)
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Indexes
    op.create_index('ix_user_vocabulary_user_id', 'user_vocabulary', ['user_id'])
    op.create_index('ix_user_vocabulary_source_passage_id', 'user_vocabulary', ['source_passage_id'])

    # Unique: user không lưu trùng từ từ cùng passage
    # (null source_passage_id được phép trùng – NULLS NOT DISTINCT cần PostgreSQL 15+)
    op.create_index(
        'uq_user_vocab_word_passage',
        'user_vocabulary',
        ['user_id', 'word', 'source_passage_id'],
        unique=True,
        postgresql_where=sa.text('source_passage_id IS NOT NULL')
    )


def downgrade() -> None:
    op.drop_index('uq_user_vocab_word_passage', table_name='user_vocabulary')
    op.drop_index('ix_user_vocabulary_source_passage_id', table_name='user_vocabulary')
    op.drop_index('ix_user_vocabulary_user_id', table_name='user_vocabulary')
    op.drop_table('user_vocabulary')
