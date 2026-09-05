"""Add contract lifecycle fields, rollover settings and user address

Revision ID: 0004_contract_lifecycle_rollover
Revises: 0003_remove_payment_term
Create Date: 2026-09-05 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004_contract_lifecycle_rollover'
down_revision: Union[str, None] = '0003_remove_payment_term'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns to users table
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('full_name', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('address', sa.Text(), nullable=True))

    # 2. Add columns to contracts table
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.add_column(sa.Column('initial_term_months', sa.Integer(), server_default='0', nullable=True))
        batch_op.add_column(sa.Column('renewal_period_months', sa.Integer(), server_default='1', nullable=True))
        batch_op.add_column(sa.Column('renewal_type', sa.String(length=32), server_default='monthly_rolling', nullable=True))
        batch_op.add_column(sa.Column('cancellation_sent_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('confirmed_end_date', sa.Date(), nullable=True))

    # 3. For PostgreSQL, add new enum values to contractstatus type
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE contractstatus ADD VALUE IF NOT EXISTS 'pending_cancellation'")
        op.execute("ALTER TYPE contractstatus ADD VALUE IF NOT EXISTS 'cancellation_confirmed'")
        op.execute("ALTER TYPE contractstatus ADD VALUE IF NOT EXISTS 'paused'")


def downgrade() -> None:
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.drop_column('confirmed_end_date')
        batch_op.drop_column('cancellation_sent_date')
        batch_op.drop_column('renewal_type')
        batch_op.drop_column('renewal_period_months')
        batch_op.drop_column('initial_term_months')

    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('address')
        batch_op.drop_column('full_name')
