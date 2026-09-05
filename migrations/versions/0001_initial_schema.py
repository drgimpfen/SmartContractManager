"""Initial baseline schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-05 16:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('hashed_password', sa.String(length=256), nullable=False),
        sa.Column('timezone', sa.String(length=64), server_default='Europe/Berlin', nullable=True),
        sa.Column('currency', sa.String(length=8), server_default='EUR', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    # 2. Providers table
    op.create_table(
        'providers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('customer_number', sa.String(length=80), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('website', sa.String(length=255), nullable=True),
        sa.Column('customer_portal', sa.String(length=255), nullable=True),
        sa.Column('cancel_url', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_providers_id'), 'providers', ['id'], unique=False)

    # 3. Tags table
    op.create_table(
        'tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tags_id'), 'tags', ['id'], unique=False)

    # 4. Contracts table
    contract_status_enum = sa.Enum('active', 'canceled', 'archived', name='contractstatus')
    frequency_enum = sa.Enum('weekly', 'biweekly', 'monthly', 'quarterly', 'yearly', name='frequency')

    op.create_table(
        'contracts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=80), server_default='Sonstiges', nullable=False),
        sa.Column('status', contract_status_enum, server_default='active', nullable=False),
        sa.Column('contract_number', sa.String(length=120), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('cancellation_notice_amount', sa.Integer(), server_default='0', nullable=True),
        sa.Column('cancellation_notice_unit', sa.String(length=16), server_default='days', nullable=True),
        sa.Column('amount', sa.Float(), server_default='0.0', nullable=True),
        sa.Column('currency', sa.String(length=8), server_default='EUR', nullable=True),
        sa.Column('frequency', frequency_enum, server_default='monthly', nullable=False),
        sa.Column('payment_term', sa.String(length=64), nullable=True),
        sa.Column('payment_method', sa.String(length=64), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['provider_id'], ['providers.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contracts_id'), 'contracts', ['id'], unique=False)

    # 5. Contract tags link table
    op.create_table(
        'contract_tags',
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tags.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('contract_id', 'tag_id')
    )

    # 6. Documents table
    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('stored_filename', sa.String(length=255), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('extracted_text', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_id'), 'documents', ['id'], unique=False)

    # 7. Price entries table
    op.create_table(
        'price_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('contract_id', sa.Integer(), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('currency', sa.String(length=8), server_default='EUR', nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['contract_id'], ['contracts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_price_entries_id'), 'price_entries', ['id'], unique=False)

    # 8. Exchange rate cache table
    op.create_table(
        'exchange_rate_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('base_currency', sa.String(length=8), nullable=False),
        sa.Column('target_currency', sa.String(length=8), nullable=False),
        sa.Column('rate', sa.Float(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_exchange_rate_cache_id'), 'exchange_rate_cache', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_exchange_rate_cache_id'), table_name='exchange_rate_cache')
    op.drop_table('exchange_rate_cache')

    op.drop_index(op.f('ix_price_entries_id'), table_name='price_entries')
    op.drop_table('price_entries')

    op.drop_index(op.f('ix_documents_id'), table_name='documents')
    op.drop_table('documents')

    op.drop_table('contract_tags')

    op.drop_index(op.f('ix_contracts_id'), table_name='contracts')
    op.drop_table('contracts')

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute('DROP TYPE IF EXISTS frequency')
        op.execute('DROP TYPE IF EXISTS contractstatus')

    op.drop_index(op.f('ix_tags_id'), table_name='tags')
    op.drop_table('tags')

    op.drop_index(op.f('ix_providers_id'), table_name='providers')
    op.drop_table('providers')

    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
