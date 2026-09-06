import pytest
from app.models import User, Contract, Provider, ContractStatus

def test_user_model(app):
    from app import db
    user = User(username="testuser", hashed_password="hashed_password")
    with app.app_context():
        db.session.add(user)
        db.session.commit()
        
        saved_user = db.session.get(User, user.id)
        assert saved_user.username == "testuser"
        assert saved_user.timezone == "Europe/Berlin"

def test_contract_model(app):
    from app import db
    with app.app_context():
        user = User(username="contractuser", hashed_password="pw")
        db.session.add(user)
        db.session.commit()

        contract = Contract(
            user_id=user.id,
            category="Internet",
            status=ContractStatus.active,
            amount=39.99
        )
        db.session.add(contract)
        db.session.commit()

        saved_contract = db.session.get(Contract, contract.id)
        assert saved_contract.amount == 39.99
        assert saved_contract.status == ContractStatus.active


def test_calculate_month_delta():
    from datetime import date
    from app.models import calculate_month_delta

    # Full year 01.01 to 31.12 = 12 months
    assert calculate_month_delta(date(2021, 1, 1), date(2021, 12, 31)) == 12

    # 6 full years 01.01.2021 to 31.12.2026 = 72 months (not 71!)
    assert calculate_month_delta(date(2021, 1, 1), date(2026, 12, 31)) == 72

    # Exact anniversary 01.01 to 01.01 next year = 12 months
    assert calculate_month_delta(date(2021, 1, 1), date(2022, 1, 1)) == 12

    # Mid-month inclusive 15.03.2021 to 14.03.2022 = 12 months
    assert calculate_month_delta(date(2021, 3, 15), date(2022, 3, 14)) == 12

    # February end of month
    assert calculate_month_delta(date(2021, 2, 1), date(2021, 2, 28)) == 1
    assert calculate_month_delta(date(2020, 2, 1), date(2020, 2, 29)) == 1  # Leap year

    # Half year 01.01 to 30.06 = 6 months
    assert calculate_month_delta(date(2021, 1, 1), date(2021, 6, 30)) == 6

    # Zero or negative ranges
    assert calculate_month_delta(date(2021, 1, 1), date(2021, 1, 1)) == 0
    assert calculate_month_delta(date(2021, 5, 1), date(2020, 5, 1)) == 0
    assert calculate_month_delta(None, date(2021, 1, 1)) == 0


def test_days_until_end_formatted(app):
    from datetime import date, timedelta
    from app.models import Contract

    with app.app_context():
        # Long term (e.g. 9429 days)
        c_long = Contract(end_date=date.today() + timedelta(days=9429))
        formatted_long = c_long.days_until_end_formatted
        assert "25" in formatted_long
        assert "10" in formatted_long

        # Month range (e.g. 150 days ~ 5 months)
        c_mid = Contract(end_date=date.today() + timedelta(days=150))
        assert "5" in c_mid.days_until_end_formatted

        # Short term (14 days)
        c_short = Contract(end_date=date.today() + timedelta(days=14))
        assert "14" in c_short.days_until_end_formatted

        # 1 day
        c_one = Contract(end_date=date.today() + timedelta(days=1))
        assert "1" in c_one.days_until_end_formatted

        # Today
        c_today = Contract(end_date=date.today())
        assert "heute" in c_today.days_until_end_formatted.lower() or "today" in c_today.days_until_end_formatted.lower()


def test_contract_initial_term_properties(app):
    from datetime import date, timedelta
    from app.models import Contract

    # Contract with explicit initial_term_end_date in the future
    future_date = date.today() + timedelta(days=90)
    c_active = Contract(
        initial_term_end_date=future_date,
        initial_term_months=12,
        cancellation_target_period="exact",
    )
    assert c_active.effective_initial_term_end_date == future_date
    assert c_active.is_in_initial_term is True
    assert c_active.initial_term_days_left == 90
    assert "Monat" in c_active.initial_term_days_left_formatted or "noch" in c_active.initial_term_days_left_formatted

    # Contract with calculated initial_term from start_date + initial_term_months (snap to end_of_month)
    c_calculated = Contract(
        start_date=date(2026, 1, 1),
        initial_term_months=6,
        cancellation_target_period="end_of_month",
    )
    # 2026-01-01 + 6 months = 2026-07-01 -> end of month = 2026-07-31
    assert c_calculated.effective_initial_term_end_date == date(2026, 7, 31)

    # Contract with initial term in the past
    past_date = date.today() - timedelta(days=100)
    c_expired = Contract(
        initial_term_end_date=past_date,
        initial_term_months=12,
    )
    assert c_expired.effective_initial_term_end_date == past_date
    assert c_expired.is_in_initial_term is False
    assert c_expired.initial_term_days_left is None
    assert c_expired.initial_term_days_left_formatted is None

    # Contract with 0 initial term months and no end date
    c_none = Contract(initial_term_months=0)
    assert c_none.effective_initial_term_end_date is None
    assert c_none.is_in_initial_term is False
    assert c_none.initial_term_days_left is None
    assert c_none.initial_term_days_left_formatted is None

    # Days left formatting edge cases
    c_today = Contract(initial_term_end_date=date.today())
    assert c_today.is_in_initial_term is True
    assert c_today.initial_term_days_left == 0
    assert c_today.initial_term_days_left_formatted == "endet heute"

    c_1day = Contract(initial_term_end_date=date.today() + timedelta(days=1))
    assert c_1day.initial_term_days_left == 1
    assert c_1day.initial_term_days_left_formatted == "noch 1 Tag"

    c_15days = Contract(initial_term_end_date=date.today() + timedelta(days=15))
    assert c_15days.initial_term_days_left == 15
    assert c_15days.initial_term_days_left_formatted == "noch 15 T."


def test_current_commitment_properties(app):
    from datetime import date, timedelta
    from app.models import Contract

    # 1. KFZ contract past initial term with fixed_period renewal (annual end of year)
    c_kfz = Contract(
        start_date=date(2021, 1, 1),
        billing_anchor_date=date(2021, 1, 1),
        initial_term_months=12,
        initial_term_end_date=date(2021, 12, 31),
        renewal_type="fixed_period",
        renewal_period_months=12,
        cancellation_target_period="end_of_year",
        cancellation_notice_amount=1,
        cancellation_notice_unit="months",
    )
    assert c_kfz.current_commitment_type == "fixed_period"
    # Should resolve to the current period end (e.g. 2026-12-31)
    assert c_kfz.current_commitment_end_date == date(2026, 12, 31)
    assert c_kfz.current_commitment_days_left is not None
    assert c_kfz.current_commitment_days_left > 0
    formatted = c_kfz.current_commitment_days_left_formatted.lower()
    assert "monat" in formatted or "month" in formatted or "t." in formatted or "day" in formatted

    # 2. Active contract within initial term
    future_date = date.today() + timedelta(days=120)
    c_initial = Contract(
        start_date=date.today() - timedelta(days=60),
        initial_term_months=6,
        initial_term_end_date=future_date,
        renewal_type="monthly_rolling",
    )
    assert c_initial.current_commitment_type == "initial_term"
    assert c_initial.current_commitment_end_date == future_date
    assert c_initial.current_commitment_days_left == 120

    # 3. Flexible rolling contract past initial term
    past_date = date.today() - timedelta(days=60)
    c_flex = Contract(
        start_date=date(2023, 1, 1),
        initial_term_end_date=past_date,
        renewal_type="monthly_rolling",
        renewal_period_months=1,
        cancellation_notice_amount=1,
        cancellation_notice_unit="months",
        cancellation_target_period="exact",
    )
    assert c_flex.current_commitment_type == "monthly_rolling"
    assert c_flex.current_commitment_end_date is not None

    # 4. Fixed-term contract (renewal_type == 'none')
    c_fixed = Contract(
        end_date=date.today() + timedelta(days=200),
        renewal_type="none",
    )
    assert c_fixed.current_commitment_type == "fixed_term"
    assert c_fixed.current_commitment_end_date == date.today() + timedelta(days=200)



