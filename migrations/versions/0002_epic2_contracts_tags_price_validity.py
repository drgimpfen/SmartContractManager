"""Epic 2: Add billing_anchor_date, tag color, and price validity intervals

Revision ID: 0002_epic2_crud_prices
Revises: 0001_initial_schema
Create Date: 2026-09-05 16:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002_epic2_crud_prices'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add billing_anchor_date to contracts
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.add_column(sa.Column('billing_anchor_date', sa.Date(), nullable=True))

    # 2. Add color to tags
    with op.batch_alter_table('tags') as batch_op:
        batch_op.add_column(sa.Column('color', sa.String(length=16), server_default='#0d6efd', nullable=False))

    # 3. Update price_entries table: add valid_from, valid_to, is_current
    with op.batch_alter_table('price_entries') as batch_op:
        batch_op.add_column(sa.Column('valid_from', sa.Date(), server_default='2025-01-01', nullable=False))
        batch_op.add_column(sa.Column('valid_to', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('is_current', sa.Boolean(), server_default=sa.true(), nullable=False))

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col['name'] for col in inspector.get_columns('price_entries')]
    if 'effective_date' in columns:
        op.execute('UPDATE price_entries SET valid_from = effective_date')
        with op.batch_alter_table('price_entries') as batch_op:
            batch_op.drop_column('effective_date')


def downgrade() -> None:
    # Reverse price_entries columns
    with op.batch_alter_table('price_entries') as batch_op:
        batch_op.add_column(sa.Column('effective_date', sa.Date(), server_default='2025-01-01', nullable=False))
    op.execute('UPDATE price_entries SET effective_date = valid_from')
    with op.batch_alter_table('price_entries') as batch_op:
        batch_op.drop_column('is_current')
        batch_op.drop_column('valid_to')
        batch_op.drop_column('valid_from')

    # Reverse tags color
    with op.batch_alter_table('tags') as batch_op:
        batch_op.drop_column('color')

    # Reverse contracts billing_anchor_date
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.drop_column('billing_anchor_date')
