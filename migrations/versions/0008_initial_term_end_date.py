"""Add initial_term_end_date to contracts

Revision ID: 0008_initial_term_end_date
Revises: 0007_cancellation_target_period
Create Date: 2026-09-06 01:27:00.000000

"""
import calendar
from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic (must be <= 32 chars).
revision: str = '0008_initial_term_end_date'
down_revision: Union[str, None] = '0007_cancellation_target_period'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_months(sourcedate: date, months: int) -> date:
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _snap_target(target_date: date, period_type: str | None) -> date:
    if not period_type or period_type == 'exact':
        return target_date
    if period_type == 'end_of_month':
        last_day = calendar.monthrange(target_date.year, target_date.month)[1]
        return date(target_date.year, target_date.month, last_day)
    elif period_type == 'end_of_quarter':
        q_month = ((target_date.month - 1) // 3 + 1) * 3
        last_day = calendar.monthrange(target_date.year, q_month)[1]
        return date(target_date.year, q_month, last_day)
    elif period_type == 'end_of_year':
        return date(target_date.year, 12, 31)
    return target_date


def upgrade() -> None:
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.add_column(
            sa.Column(
                'initial_term_end_date',
                sa.Date(),
                nullable=True,
            )
        )

    # Populate initial_term_end_date for existing contracts with initial_term_months > 0
    bind = op.get_bind()
    try:
        contracts = bind.execute(
            sa.text(
                "SELECT id, start_date, initial_term_months, cancellation_target_period "
                "FROM contracts WHERE initial_term_months IS NOT NULL AND initial_term_months > 0 AND start_date IS NOT NULL"
            )
        ).fetchall()

        for row in contracts:
            c_id = row[0]
            c_start = row[1]
            c_months = row[2]
            c_target = row[3] if len(row) > 3 else 'exact'

            if isinstance(c_start, str):
                c_start = date.fromisoformat(c_start)

            if c_start and c_months:
                end_d = _snap_target(_add_months(c_start, c_months), c_target)
                bind.execute(
                    sa.text("UPDATE contracts SET initial_term_end_date = :end_d WHERE id = :c_id"),
                    {"end_d": end_d, "c_id": c_id},
                )
    except Exception:
        # Ignore during fresh headless runs if table is empty
        pass


def downgrade() -> None:
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.drop_column('initial_term_end_date')
