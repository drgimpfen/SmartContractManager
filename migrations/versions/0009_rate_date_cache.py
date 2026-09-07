"""Add rate_date to exchange_rate_cache and unique constraint

Revision ID: 0009_rate_date_cache
Revises: 0008_initial_term_end_date
Create Date: 2026-09-08 00:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic (must be <= 32 chars).
revision: str = '0009_rate_date_cache'
down_revision: Union[str, None] = '0008_initial_term_end_date'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add column as nullable initially
    with op.batch_alter_table('exchange_rate_cache') as batch_op:
        batch_op.add_column(sa.Column('rate_date', sa.Date(), nullable=True))
        batch_op.create_index('ix_exchange_rate_cache_rate_date', ['rate_date'], unique=False)

    # 2. Backfill rate_date from last_updated or fallback to current_date
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == 'sqlite':
        op.execute(
            "UPDATE exchange_rate_cache SET rate_date = COALESCE(date(last_updated), date('now')) WHERE rate_date IS NULL"
        )
    else:
        op.execute(
            "UPDATE exchange_rate_cache SET rate_date = COALESCE(CAST(last_updated AS DATE), CURRENT_DATE) WHERE rate_date IS NULL"
        )

    # 3. Clean up any existing duplicate pairs for the same date before applying unique constraint
    op.execute("""
        DELETE FROM exchange_rate_cache
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM exchange_rate_cache
            GROUP BY base_currency, target_currency, rate_date
        )
    """)

    # 4. Alter column to NOT NULL and create unique constraint via batch_alter_table
    with op.batch_alter_table('exchange_rate_cache') as batch_op:
        batch_op.alter_column('rate_date', nullable=False)
        batch_op.create_unique_constraint(
            'uq_exchange_rate_cache_pair_date',
            ['base_currency', 'target_currency', 'rate_date']
        )


def downgrade() -> None:
    with op.batch_alter_table('exchange_rate_cache') as batch_op:
        batch_op.drop_constraint('uq_exchange_rate_cache_pair_date', type_='unique')
        batch_op.drop_index('ix_exchange_rate_cache_rate_date')
        batch_op.drop_column('rate_date')
