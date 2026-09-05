"""Add title to contracts, add notes table, and add scheduled to contractstatus

Revision ID: 0006_title_notes_scheduled
Revises: 0005_contract_is_archived
Create Date: 2026-09-06 00:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic (must be <= 32 chars).
revision: str = '0006_title_notes_scheduled'
down_revision: Union[str, None] = '0005_contract_is_archived'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. For PostgreSQL, add scheduled to contractstatus enum
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE contractstatus ADD VALUE IF NOT EXISTS 'scheduled'")

    # 2. Add title column to contracts
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.add_column(sa.Column('title', sa.String(length=120), server_default='', nullable=False))

    # 3. Create notes table
    op.create_table(
        'notes',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('contract_id', sa.Integer(), sa.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('provider_id', sa.Integer(), sa.ForeignKey('providers.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 4. Data migration: Initialize title from category for existing contracts
    op.execute("UPDATE contracts SET title = category WHERE title IS NULL OR title = ''")

    # 5. Data migration: Migrate existing contract notes into notes table
    op.execute("""
        INSERT INTO notes (user_id, contract_id, content, created_at)
        SELECT user_id, id, notes, created_at
        FROM contracts
        WHERE notes IS NOT NULL AND TRIM(notes) != ''
    """)


def downgrade() -> None:
    op.drop_table('notes')

    with op.batch_alter_table('contracts') as batch_op:
        batch_op.drop_column('title')
