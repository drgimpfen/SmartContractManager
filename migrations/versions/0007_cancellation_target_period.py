"""Add cancellation_target_period to contracts

Revision ID: 0007_cancellation_target_period
Revises: 0006_title_notes_scheduled
Create Date: 2026-09-06 01:08:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic (must be <= 32 chars).
revision: str = '0007_cancellation_target_period'
down_revision: Union[str, None] = '0006_title_notes_scheduled'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.add_column(
            sa.Column(
                'cancellation_target_period',
                sa.String(length=32),
                server_default='exact',
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.drop_column('cancellation_target_period')
