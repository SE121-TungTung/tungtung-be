"""add_irt_columns_to_question_bank

Revision ID: c2b3d4e5f6a7
Revises: c1a2b3d4e5f6
Create Date: 2026-10-12 16:30:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2b3d4e5f6a7'
down_revision: Union[str, None] = 'c1a2b3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = [c['name'] for c in inspector.get_columns('question_bank')]

    if 'irt_discrimination' not in existing_cols:
        op.add_column('question_bank', sa.Column('irt_discrimination', sa.Numeric(6, 4), server_default='1.0000', nullable=False))
    if 'irt_difficulty' not in existing_cols:
        op.add_column('question_bank', sa.Column('irt_difficulty', sa.Numeric(6, 4), server_default='0.0000', nullable=False))
    if 'irt_guessing' not in existing_cols:
        op.add_column('question_bank', sa.Column('irt_guessing', sa.Numeric(6, 4), server_default='0.2500', nullable=False))
    if 'irt_calibrated' not in existing_cols:
        op.add_column('question_bank', sa.Column('irt_calibrated', sa.Boolean(), server_default='false', nullable=False))
    if 'irt_calibrated_at' not in existing_cols:
        op.add_column('question_bank', sa.Column('irt_calibrated_at', sa.DateTime(timezone=True), nullable=True))
    if 'is_cat_eligible' not in existing_cols:
        op.add_column('question_bank', sa.Column('is_cat_eligible', sa.Boolean(), server_default='false', nullable=False))

    # Partial index for fast query of ready questions for CAT
    op.create_index(
        'idx_qbank_cat_ready',
        'question_bank',
        ['skill_area', 'is_cat_eligible', 'irt_calibrated'],
        postgresql_where=sa.text("deleted_at IS NULL AND status = 'active'")
    )


def downgrade() -> None:
    op.drop_index('idx_qbank_cat_ready', table_name='question_bank')
    op.drop_column('question_bank', 'is_cat_eligible')
    op.drop_column('question_bank', 'irt_calibrated_at')
    op.drop_column('question_bank', 'irt_calibrated')
    op.drop_column('question_bank', 'irt_guessing')
    op.drop_column('question_bank', 'irt_difficulty')
    op.drop_column('question_bank', 'irt_discrimination')
