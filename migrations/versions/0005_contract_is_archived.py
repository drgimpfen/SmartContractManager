"""Add is_archived boolean column to contracts table and migrate archived status

Revision ID: 0005_contract_is_archived
Revises: 0004_contract_lifecycle_rollover
Create Date: 2026-09-06 00:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_contract_is_archived'
down_revision: Union[str, None] = '0004_contract_lifecycle_rollover'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add is_archived column to contracts
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.add_column(sa.Column('is_archived', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.create_index('ix_contracts_is_archived', ['is_archived'], unique=False)

    # 2. Data migration: contracts with status 'archived' become is_archived=True and status='canceled'
    op.execute("UPDATE contracts SET is_archived = true, status = 'canceled' WHERE status = 'archived'")


def downgrade() -> None:
    # Revert data: contracts with is_archived=True become status='archived'
    op.execute("UPDATE contracts SET status = 'archived' WHERE is_archived = true")

    with op.batch_alter_table('contracts') as batch_op:
        batch_op.drop_index('ix_contracts_is_archived')
        batch_op.drop_column('is_archived')
