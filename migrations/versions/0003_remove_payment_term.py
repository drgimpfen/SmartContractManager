"""Remove payment_term column from contracts table

Revision ID: 0003_remove_payment_term
Revises: 0002_epic2_crud_prices
Create Date: 2026-09-05 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003_remove_payment_term'
down_revision: Union[str, None] = '0002_epic2_crud_prices'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.drop_column('payment_term')


def downgrade() -> None:
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.add_column(sa.Column('payment_term', sa.String(length=64), nullable=True))
