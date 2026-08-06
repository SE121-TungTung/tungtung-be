"""add_wallet

Revision ID: fd9941a8baf5
Revises: 4153799f4922
Create Date: 2026-06-13 11:26:11.231131

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fd9941a8baf5'
down_revision: Union[str, None] = '4153799f4922'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('wallet_transactions',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('type', sa.Enum('credit', 'debit', name='transaction_type', native_enum=False), nullable=False),
    sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('balance_after', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('reference_type', sa.Enum('tuition', 'salary', 'refund', 'top_up', 'withdrawal', name='wallet_ref_type', native_enum=False), nullable=False),
    sa.Column('reference_id', sa.UUID(), nullable=True),
    sa.Column('status', sa.Enum('pending', 'approved', 'rejected', name='wallet_tx_status', native_enum=False), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_by', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_wallet_transactions_status', 'wallet_transactions', ['status'], unique=False)
    op.create_index('ix_wallet_transactions_user_id', 'wallet_transactions', ['user_id'], unique=False)
    op.add_column('users', sa.Column('wallet_balance', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'))


def downgrade() -> None:
    op.drop_column('users', 'wallet_balance')
    op.drop_index('ix_wallet_transactions_user_id', table_name='wallet_transactions')
    op.drop_index('ix_wallet_transactions_status', table_name='wallet_transactions')
    op.drop_table('wallet_transactions')
