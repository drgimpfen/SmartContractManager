from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest

from app.models import Contract, ContractStatus, Frequency, PriceEntry
from app.services.financial_service import (
    FinancialService,
    normalize_to_monthly,
    get_contract_price_on_date,
    is_contract_active_on_date,
)


class DummyCurrencyService:
    def __init__(self, rates=None):
        self.rates = rates or {}

    def get_rate(self, base, target):
        if base == target:
            return 1.0
        return self.rates.get((base, target), 1.0)

    def convert(self, amount, from_curr, to_curr):
        if not amount:
            return 0.0
        return round(amount * self.get_rate(from_curr, to_curr), 2)


def test_normalize_to_monthly():
    assert normalize_to_monthly(0.0, Frequency.monthly) == 0.0
    assert normalize_to_monthly(None, Frequency.monthly) == 0.0

    # Monthly
    assert normalize_to_monthly(30.0, Frequency.monthly) == 30.0
    assert normalize_to_monthly(30.0, "monthly") == 30.0

    # Weekly: 10 * 52 / 12 = 43.3333...
    assert round(normalize_to_monthly(10.0, Frequency.weekly), 2) == 43.33
    assert round(normalize_to_monthly(10.0, "weekly"), 2) == 43.33

    # Biweekly: 20 * 26 / 12 = 43.3333...
    assert round(normalize_to_monthly(20.0, Frequency.biweekly), 2) == 43.33
    assert round(normalize_to_monthly(20.0, "biweekly"), 2) == 43.33

    # Quarterly: 90 / 3 = 30.0
    assert normalize_to_monthly(90.0, Frequency.quarterly) == 30.0
    assert normalize_to_monthly(90.0, "quarterly") == 30.0

    # Yearly: 120 / 12 = 10.0
    assert normalize_to_monthly(120.0, Frequency.yearly) == 10.0
    assert normalize_to_monthly(120.0, "yearly") == 10.0

    # Unknown
    assert normalize_to_monthly(50.0, "custom") == 50.0


def test_contract_price_on_date():
    c = Contract(amount=25.0, currency="EUR")
    p1 = PriceEntry(amount=20.0, currency="EUR", valid_from=date(2026, 1, 1), valid_to=date(2026, 5, 31))
    p2 = PriceEntry(amount=30.0, currency="EUR", valid_from=date(2026, 6, 1), valid_to=None)
    c.price_history = [p2, p1]

    amt, curr = get_contract_price_on_date(c, date(2026, 3, 15))
    assert amt == 20.0
    assert curr == "EUR"

    amt, curr = get_contract_price_on_date(c, date(2026, 7, 1))
    assert amt == 30.0
    assert curr == "EUR"

    # Before price history
    c2 = Contract(amount=15.0, currency="USD", price_history=[])
    amt2, curr2 = get_contract_price_on_date(c2, date(2026, 1, 1))
    assert amt2 == 15.0
    assert curr2 == "USD"


def test_is_contract_active_on_date():
    c_active = Contract(status=ContractStatus.active, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    assert is_contract_active_on_date(c_active, date(2026, 6, 1)) is True
    assert is_contract_active_on_date(c_active, date(2025, 12, 31)) is False
    assert is_contract_active_on_date(c_active, date(2027, 1, 1)) is False

    c_canceled = Contract(status=ContractStatus.canceled)
    assert is_contract_active_on_date(c_canceled, date(2026, 6, 1)) is False


def test_calculate_monthly_and_annual_budget():
    dummy_curr = DummyCurrencyService({("USD", "EUR"): 0.80})
    fin_svc = FinancialService(currency_service=dummy_curr)

    c1 = Contract(
        status=ContractStatus.active,
        category="Streaming",
        amount=15.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 1, 1),
    )
    c2 = Contract(
        status=ContractStatus.active,
        category="Gym",
        amount=120.0,
        currency="EUR",
        frequency=Frequency.yearly,  # 10.0 EUR/mo
        start_date=date(2026, 1, 1),
    )
    c3 = Contract(
        status=ContractStatus.active,
        category="Software",
        amount=50.0,
        currency="USD",  # 50 * 0.8 = 40 EUR/mo
        frequency=Frequency.monthly,
        start_date=date(2026, 1, 1),
    )
    c_inactive = Contract(
        status=ContractStatus.canceled,
        category="Old",
        amount=100.0,
        currency="EUR",
        frequency=Frequency.monthly,
    )

    contracts = [c1, c2, c3, c_inactive]
    # Expected: 15.0 + 10.0 + 40.0 = 65.0 EUR
    monthly_budget = fin_svc.calculate_monthly_budget(contracts, target_currency="EUR", as_of=date(2026, 6, 1))
    assert monthly_budget == 65.0

    annual_budget = fin_svc.calculate_annual_budget(contracts, target_currency="EUR", as_of=date(2026, 6, 1))
    assert annual_budget == 780.0


def test_calculate_current_month_expenses():
    dummy_curr = DummyCurrencyService()
    fin_svc = FinancialService(currency_service=dummy_curr)

    # Contract 1: Monthly on the 10th
    c1 = Contract(
        status=ContractStatus.active,
        amount=25.0,
        currency="EUR",
        frequency=Frequency.monthly,
        billing_anchor_date=date(2026, 1, 10),
    )
    # Contract 2: Quarterly, anchor Jan 15th -> Jan, Apr, Jul, Oct.
    c2 = Contract(
        status=ContractStatus.active,
        amount=90.0,
        currency="EUR",
        frequency=Frequency.quarterly,
        billing_anchor_date=date(2026, 1, 15),
    )
    # Contract 3: Contract without anchor date, 10 EUR/mo
    c3 = Contract(
        status=ContractStatus.active,
        amount=10.0,
        currency="EUR",
        frequency=Frequency.monthly,
        billing_anchor_date=None,
    )

    contracts = [c1, c2, c3]

    # In April 2026: c1 (25) + c2 (90) + c3 (10) = 125.0
    apr_expenses = fin_svc.calculate_current_month_expenses(contracts, "EUR", as_of=date(2026, 4, 1))
    assert apr_expenses == 125.0

    # In May 2026: c1 (25) + c2 (0, next in July) + c3 (10) = 35.0
    may_expenses = fin_svc.calculate_current_month_expenses(contracts, "EUR", as_of=date(2026, 5, 1))
    assert may_expenses == 35.0


def test_cashflow_projection_12_months_and_intervals():
    dummy_curr = DummyCurrencyService()
    fin_svc = FinancialService(currency_service=dummy_curr)

    # Monthly contract, 20 EUR
    c_monthly = Contract(
        status=ContractStatus.active,
        amount=20.0,
        currency="EUR",
        frequency=Frequency.monthly,
        billing_anchor_date=date(2026, 1, 5),
    )

    # Quarterly contract, 60 EUR in Mar, Jun, Sep, Dec
    c_quarterly = Contract(
        status=ContractStatus.active,
        amount=60.0,
        currency="EUR",
        frequency=Frequency.quarterly,
        billing_anchor_date=date(2026, 3, 15),
    )

    # Yearly contract, 120 EUR in November
    c_yearly = Contract(
        status=ContractStatus.active,
        amount=120.0,
        currency="EUR",
        frequency=Frequency.yearly,
        billing_anchor_date=date(2025, 11, 20),
    )

    contracts = [c_monthly, c_quarterly, c_yearly]
    proj = fin_svc.calculate_cashflow_projection(contracts, "EUR", as_of=date(2026, 1, 1), months=12)

    assert len(proj) == 12
    # Month 0: Jan 2026 -> only monthly (20)
    assert proj[0]["month"] == "2026-01"
    assert proj[0]["amount"] == 20.0

    # Month 1: Feb 2026 -> only monthly (20)
    assert proj[1]["month"] == "2026-02"
    assert proj[1]["amount"] == 20.0

    # Month 2: Mar 2026 -> monthly (20) + quarterly (60) = 80.0
    assert proj[2]["month"] == "2026-03"
    assert proj[2]["amount"] == 80.0

    # Month 10: Nov 2026 -> monthly (20) + yearly (120) = 140.0
    assert proj[10]["month"] == "2026-11"
    assert proj[10]["amount"] == 140.0

    # Month 11: Dec 2026 -> monthly (20) + quarterly (60) = 80.0
    assert proj[11]["month"] == "2026-12"
    assert proj[11]["amount"] == 80.0


def test_cashflow_weekly_and_biweekly():
    dummy_curr = DummyCurrencyService()
    fin_svc = FinancialService(currency_service=dummy_curr)

    # Weekly contract: 10 EUR starting on 2026-01-01 (Thu)
    # Jan 2026 has 5 Thursdays: Jan 1, 8, 15, 22, 29 -> 5 * 10 = 50 EUR
    c_weekly = Contract(
        status=ContractStatus.active,
        amount=10.0,
        currency="EUR",
        frequency=Frequency.weekly,
        billing_anchor_date=date(2026, 1, 1),
    )

    proj = fin_svc.calculate_cashflow_projection([c_weekly], "EUR", as_of=date(2026, 1, 1), months=2)
    assert proj[0]["month"] == "2026-01"
    assert proj[0]["amount"] == 50.0
    # Feb 2026 has 4 Thursdays: Feb 5, 12, 19, 26 -> 40 EUR
    assert proj[1]["month"] == "2026-02"
    assert proj[1]["amount"] == 40.0


def test_cashflow_end_of_month_pinning_and_leap_year():
    dummy_curr = DummyCurrencyService()
    fin_svc = FinancialService(currency_service=dummy_curr)

    # Anchor on Jan 31 in a leap year (2028)
    c_eom = Contract(
        status=ContractStatus.active,
        amount=100.0,
        currency="EUR",
        frequency=Frequency.monthly,
        billing_anchor_date=date(2028, 1, 31),
    )

    proj = fin_svc.calculate_cashflow_projection([c_eom], "EUR", as_of=date(2028, 1, 1), months=3)
    # Jan, Feb (leap year 29 days), Mar
    assert proj[0]["amount"] == 100.0
    assert proj[1]["amount"] == 100.0
    assert proj[2]["amount"] == 100.0


def test_cashflow_price_change_mid_year():
    dummy_curr = DummyCurrencyService()
    fin_svc = FinancialService(currency_service=dummy_curr)

    c = Contract(
        status=ContractStatus.active,
        amount=50.0,
        currency="EUR",
        frequency=Frequency.monthly,
        billing_anchor_date=date(2026, 1, 1),
    )
    # Price was 50 EUR from Jan to May, then increases to 75 EUR from June onward
    p1 = PriceEntry(amount=50.0, currency="EUR", valid_from=date(2026, 1, 1), valid_to=date(2026, 5, 31))
    p2 = PriceEntry(amount=75.0, currency="EUR", valid_from=date(2026, 6, 1), valid_to=None)
    c.price_history = [p2, p1]

    proj = fin_svc.calculate_cashflow_projection([c], "EUR", as_of=date(2026, 1, 1), months=12)
    # Months 0-4 (Jan-May) should be 50 EUR
    for m in range(5):
        assert proj[m]["amount"] == 50.0
    # Months 5-11 (Jun-Dec) should be 75 EUR
    for m in range(5, 12):
        assert proj[m]["amount"] == 75.0


def test_cashflow_contract_start_and_end_date_cutoffs():
    dummy_curr = DummyCurrencyService()
    fin_svc = FinancialService(currency_service=dummy_curr)

    # Contract starts March 1, ends July 31
    c = Contract(
        status=ContractStatus.active,
        amount=30.0,
        currency="EUR",
        frequency=Frequency.monthly,
        billing_anchor_date=date(2026, 1, 1),
        start_date=date(2026, 3, 1),
        end_date=date(2026, 7, 31),
    )

    proj = fin_svc.calculate_cashflow_projection([c], "EUR", as_of=date(2026, 1, 1), months=12)
    assert proj[0]["amount"] == 0.0  # Jan
    assert proj[1]["amount"] == 0.0  # Feb
    assert proj[2]["amount"] == 30.0 # Mar
    assert proj[3]["amount"] == 30.0 # Apr
    assert proj[4]["amount"] == 30.0 # May
    assert proj[5]["amount"] == 30.0 # Jun
    assert proj[6]["amount"] == 30.0 # Jul
    assert proj[7]["amount"] == 0.0  # Aug
    assert proj[8]["amount"] == 0.0  # Sep


def test_category_distribution():
    dummy_curr = DummyCurrencyService()
    fin_svc = FinancialService(currency_service=dummy_curr)

    c1 = Contract(status=ContractStatus.active, category="Internet", amount=40.0, currency="EUR", frequency=Frequency.monthly)
    c2 = Contract(status=ContractStatus.active, category="Streaming", amount=15.0, currency="EUR", frequency=Frequency.monthly)
    c3 = Contract(status=ContractStatus.active, category="Streaming", amount=12.0, currency="EUR", frequency=Frequency.monthly)
    c4 = Contract(status=ContractStatus.active, category="Insurance", amount=360.0, currency="EUR", frequency=Frequency.yearly) # 30 EUR/mo

    dist = fin_svc.calculate_category_distribution([c1, c2, c3, c4], "EUR")
    assert len(dist) == 3
    # Sorted descending
    assert dist[0]["category"] == "Internet"
    assert dist[0]["value"] == 40.0
    assert dist[1]["category"] == "Insurance"
    assert dist[1]["value"] == 30.0
    assert dist[2]["category"] == "Streaming"
    assert dist[2]["value"] == 27.0


def test_critical_deadlines_and_missing_notice():
    fin_svc = FinancialService()
    today = date(2026, 9, 1)

    # Critical: end_date Oct 15, notice 30 days -> deadline Sep 15 (within 14 days of today)
    c_crit1 = Contract(
        status=ContractStatus.active,
        contract_number="C-001",
        end_date=date(2026, 10, 15),
        cancellation_notice_amount=30,
        cancellation_notice_unit="days",
    )
    # Critical in weeks: end_date Sep 20, notice 2 weeks -> deadline Sep 6 (5 days away)
    c_crit2 = Contract(
        status=ContractStatus.active,
        contract_number="C-002",
        end_date=date(2026, 9, 20),
        cancellation_notice_amount=2,
        cancellation_notice_unit="weeks",
    )
    # Critical in months: end_date Nov 1, notice 2 months -> deadline Sep 1 (today!)
    c_crit3 = Contract(
        status=ContractStatus.active,
        contract_number="C-003",
        end_date=date(2026, 11, 1),
        cancellation_notice_amount=2,
        cancellation_notice_unit="months",
    )
    # Not critical: end_date next year
    c_safe = Contract(
        status=ContractStatus.active,
        contract_number="C-SAFE",
        end_date=date(2027, 9, 1),
        cancellation_notice_amount=1,
        cancellation_notice_unit="months",
    )
    # Missing notice: active but no notice amount
    c_missing = Contract(
        status=ContractStatus.active,
        contract_number="C-MISSING",
        cancellation_notice_amount=0,
    )

    contracts = [c_crit1, c_crit2, c_crit3, c_safe, c_missing]
    deadlines = fin_svc.get_critical_deadlines(contracts, as_of=today, horizon_days=30)
    assert len(deadlines) == 3
    numbers = [c.contract_number for c in deadlines]
    assert "C-001" in numbers
    assert "C-002" in numbers
    assert "C-003" in numbers
    assert "C-SAFE" not in numbers

    missing = fin_svc.get_missing_notice(contracts)
    assert len(missing) == 1
    assert missing[0].contract_number == "C-MISSING"


def test_fixed_term_excluded_from_missing_notice_and_critical_deadlines():
    fin_svc = FinancialService()
    today = date(2026, 9, 1)

    # Fixed term contract ending in 10 days, no notice period configured
    c_fixed = Contract(
        status=ContractStatus.active,
        contract_number="C-FIXED",
        renewal_type="none",
        end_date=today + timedelta(days=10),
        cancellation_notice_amount=0,
    )

    # Standard rolling contract missing notice period
    c_rolling_missing = Contract(
        status=ContractStatus.active,
        contract_number="C-ROLLING",
        renewal_type="monthly_rolling",
        cancellation_notice_amount=0,
    )

    contracts = [c_fixed, c_rolling_missing]

    # Fixed term contract must not appear in missing notice
    missing = fin_svc.get_missing_notice(contracts)
    assert len(missing) == 1
    assert missing[0].contract_number == "C-ROLLING"

    # Fixed term contract must not appear in critical deadlines (it terminates automatically)
    deadlines = fin_svc.get_critical_deadlines(contracts, as_of=today, horizon_days=30)
    assert len(deadlines) == 0


def test_financial_service_additional_edge_cases():
    fin_svc = FinancialService()

    # 1. Zero months projection with active contract
    c_act = Contract(status=ContractStatus.active, billing_anchor_date=date(2026, 1, 1))
    assert fin_svc.calculate_cashflow_projection([c_act], months=0) == []

    # 2. Contract without anchor date in _get_due_dates_in_range
    c_no_anchor = Contract(billing_anchor_date=None)
    assert fin_svc._get_due_dates_in_range(c_no_anchor, date(2026, 1, 1), date(2026, 12, 31)) == []

    # 3. Weekly contract with end_date cutting off inside candidate loop
    c_weekly_end = Contract(
        status=ContractStatus.active,
        frequency=Frequency.weekly,
        billing_anchor_date=date(2026, 1, 1),
        end_date=date(2026, 1, 10),
    )
    due_dates_weekly = fin_svc._get_due_dates_in_range(c_weekly_end, date(2026, 1, 1), date(2026, 1, 31))
    assert due_dates_weekly == [date(2026, 1, 1), date(2026, 1, 8)]

    # 4. Monthly contract with end_date cutting off inside candidate loop
    c_monthly_end = Contract(
        status=ContractStatus.active,
        frequency=Frequency.monthly,
        billing_anchor_date=date(2026, 1, 1),
        end_date=date(2026, 2, 15),
    )
    due_dates_monthly = fin_svc._get_due_dates_in_range(c_monthly_end, date(2026, 1, 1), date(2026, 5, 31))
    assert due_dates_monthly == [date(2026, 1, 1), date(2026, 2, 1)]

    # 5. Empty category defaults to "Sonstiges"
    c_no_cat = Contract(status=ContractStatus.active, category=None, amount=10.0, currency="EUR", frequency=Frequency.monthly)
    dist = fin_svc.calculate_category_distribution([c_no_cat], "EUR")
    assert len(dist) == 1
    assert dist[0]["category"] == "Sonstiges"

    # 6. Unknown notice unit fallback to days
    c_custom_unit = Contract(
        status=ContractStatus.active,
        contract_number="C-CUSTOM",
        end_date=date(2026, 9, 10),
        cancellation_notice_amount=5,
        cancellation_notice_unit="hours", # unknown unit
    )
    deadlines = fin_svc.get_critical_deadlines([c_custom_unit], as_of=date(2026, 9, 1), horizon_days=30)
    assert len(deadlines) == 1


def test_inactive_contracts_ignored_in_all_methods():
    fin_svc = FinancialService()
    c_inactive = Contract(
        status=ContractStatus.canceled,
        amount=100.0,
        currency="EUR",
        billing_anchor_date=date(2026, 1, 1),
    )

    # When all contracts are inactive, returns empty/zero
    assert fin_svc.calculate_current_month_expenses([c_inactive], "EUR", as_of=date(2026, 1, 1)) == 0.0
    assert fin_svc.calculate_cashflow_projection([c_inactive], "EUR", as_of=date(2026, 1, 1), months=1) == []
    assert fin_svc.calculate_category_distribution([c_inactive], "EUR", as_of=date(2026, 1, 1)) == []

    # When mixed with active contract, inactive is skipped
    c_active = Contract(
        status=ContractStatus.active,
        amount=10.0,
        currency="EUR",
        frequency=Frequency.monthly,
        billing_anchor_date=date(2026, 1, 1),
    )
    proj_mixed = fin_svc.calculate_cashflow_projection([c_active, c_inactive], "EUR", as_of=date(2026, 1, 1), months=1)
    assert proj_mixed[0]["amount"] == 10.0


def test_calculate_contract_cost_summary_fixed_term():
    fin_svc = FinancialService()

    # Fixed 1-year contract: 50 EUR/month for 12 months = 600 EUR
    c = Contract(
        status=ContractStatus.active,
        amount=50.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        billing_anchor_date=date(2026, 1, 1),
    )

    # Reference date middle of year (June 15, 2026)
    summary = fin_svc.calculate_contract_cost_summary(c, as_of=date(2026, 6, 15))
    assert summary["is_fixed_term"] is True
    assert summary["currency"] == "EUR"
    assert summary["total_amount"] == 600.0
    assert summary["paid_amount"] == 300.0 # Jan, Feb, Mar, Apr, May, Jun = 6 payments
    assert summary["remaining_amount"] == 300.0 # Jul, Aug, Sep, Oct, Nov, Dec = 6 payments
    assert summary["total_payments"] == 12
    assert summary["paid_payments"] == 6
    assert summary["remaining_payments"] == 6


def test_calculate_contract_cost_summary_with_price_history():
    fin_svc = FinancialService()

    # Fixed 1-year contract with price change in June
    c = Contract(
        status=ContractStatus.active,
        amount=60.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        billing_anchor_date=date(2026, 1, 1),
    )
    p1 = PriceEntry(amount=40.0, currency="EUR", valid_from=date(2026, 1, 1), valid_to=date(2026, 5, 31))
    p2 = PriceEntry(amount=60.0, currency="EUR", valid_from=date(2026, 6, 1), valid_to=None)
    c.price_history = [p1, p2]

    # Jan-May: 5 * 40 = 200 EUR; Jun-Dec: 7 * 60 = 420 EUR; Total = 620 EUR
    # As of June 15, 2026: Jan-Jun = 200 + 60 = 260 EUR paid, 6 * 60 = 360 EUR remaining
    summary = fin_svc.calculate_contract_cost_summary(c, as_of=date(2026, 6, 15))
    assert summary["is_fixed_term"] is True
    assert summary["total_amount"] == 620.0
    assert summary["paid_amount"] == 260.0
    assert summary["remaining_amount"] == 360.0
    assert summary["total_payments"] == 12
    assert summary["paid_payments"] == 6
    assert summary["remaining_payments"] == 6


def test_calculate_contract_cost_summary_open_ended():
    fin_svc = FinancialService()

    # Open-ended contract: 30 EUR/month starting Jan 1, 2026
    c = Contract(
        status=ContractStatus.active,
        amount=30.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 1, 1),
        end_date=None,
        billing_anchor_date=date(2026, 1, 1),
    )

    # As of April 10, 2026: 4 payments (Jan 1, Feb 1, Mar 1, Apr 1) = 120 EUR
    # Annual amount: 30 * 12 = 360 EUR
    summary = fin_svc.calculate_contract_cost_summary(c, as_of=date(2026, 4, 10))
    assert summary["is_fixed_term"] is False
    assert summary["currency"] == "EUR"
    assert summary["paid_amount"] == 120.0
    assert summary["paid_payments"] == 4
    assert summary["annual_amount"] == 360.0


def test_calculate_contract_cost_summary_fixed_period_renewal():
    fin_svc = FinancialService()

    # Open-ended contract with expired initial term and fixed 12-month annual renewal (like KFZ)
    c = Contract(
        status=ContractStatus.active,
        amount=500.0,
        currency="EUR",
        frequency=Frequency.yearly,
        start_date=date(2021, 1, 1),
        billing_anchor_date=date(2021, 1, 1),
        end_date=None,
        initial_term_months=12,
        initial_term_end_date=date(2021, 12, 31),
        renewal_type="fixed_period",
        renewal_period_months=12,
        cancellation_target_period="end_of_year",
        cancellation_notice_amount=1,
        cancellation_notice_unit="months",
    )

    as_of_date = date(2026, 9, 1)
    summary = fin_svc.calculate_contract_cost_summary(c, as_of=as_of_date)
    assert summary["is_fixed_term"] is False

    init_c = summary["initial_commitment"]
    assert init_c is not None
    assert init_c["is_active"] is False
    assert init_c["months"] == 12
    assert init_c["end_date"] == date(2021, 12, 31)
    assert init_c["renewal_type"] == "fixed_period"

    curr_p = summary["current_period_commitment"]
    assert curr_p is not None
    assert curr_p["bound_until"] == date(2026, 12, 31)
    assert curr_p["months"] == 12
    assert curr_p["total_amount"] == 500.0
    assert curr_p["initial_months"] == 12
    assert curr_p["initial_end_date"] == date(2021, 12, 31)


def test_calculate_contract_cost_summary_no_anchor_fallback():
    fin_svc = FinancialService()

    # Contract with start_date but no billing_anchor_date
    c = Contract(
        status=ContractStatus.active,
        amount=100.0,
        currency="USD",
        frequency=Frequency.quarterly,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        billing_anchor_date=None,
    )

    summary = fin_svc.calculate_contract_cost_summary(c, as_of=date(2026, 5, 1))
    assert summary["is_fixed_term"] is True
    assert summary["currency"] == "USD"
    # Due dates: Jan 1, Apr 1, Jul 1, Oct 1 = 4 payments * 100 = 400 USD
    assert summary["total_amount"] == 400.0
    assert summary["paid_amount"] == 200.0 # Jan 1, Apr 1
    assert summary["remaining_amount"] == 200.0 # Jul 1, Oct 1
    assert summary["total_payments"] == 4
    assert summary["paid_payments"] == 2
    assert summary["remaining_payments"] == 2


def test_calculate_provider_summary():
    dummy_curr = DummyCurrencyService(rates={("USD", "EUR"): 0.85})
    fin_svc = FinancialService(currency_service=dummy_curr)

    c1 = Contract(
        status=ContractStatus.active,
        amount=50.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 1, 1),
        end_date=None,
        billing_anchor_date=date(2026, 1, 1),
    )
    c2 = Contract(
        status=ContractStatus.active,
        amount=100.0,
        currency="USD",
        frequency=Frequency.quarterly,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        billing_anchor_date=date(2026, 1, 1),
    )
    c3 = Contract(
        status=ContractStatus.canceled,
        amount=20.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        billing_anchor_date=date(2025, 1, 1),
    )

    contracts = [c1, c2, c3]
    # As of May 1, 2026
    # c1 active monthly: 50.0 EUR
    # c2 active monthly in EUR: 100 USD * 0.85 = 85 EUR / 3 = 28.33 EUR
    # c3 is canceled -> 0 monthly
    # total monthly spend: 50 + 28.33 = 78.33 EUR
    summary = fin_svc.calculate_provider_summary(contracts, target_currency="EUR", as_of=date(2026, 5, 1))

    assert summary["total_contracts"] == 3
    assert summary["active_count"] == 2
    assert summary["canceled_count"] == 1
    assert summary["archived_count"] == 0
    assert summary["monthly_spend"] == 78.33
    assert summary["annual_projected"] == round(78.33 * 12, 2)
    assert summary["has_fixed_term"] is True
    assert summary["total_paid"] > 0
    assert summary["total_remaining"] is not None
    assert summary["total_cost"] == round(summary["total_paid"] + summary["total_remaining"], 2)


def test_cashflow_committed_vs_flexible_split():
    """Cashflow forecast accurately splits committed vs flexible amounts across initial_term_end_date."""
    fin_svc = FinancialService()

    # Contract 1: monthly rolling with initial term until 2026-06-30
    c1 = Contract(
        id=1,
        title="Fiber Internet",
        category="Internet",
        status=ContractStatus.active,
        amount=50.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 1, 1),
        billing_anchor_date=date(2026, 1, 1),
        initial_term_end_date=date(2026, 6, 30),
        renewal_type="monthly_rolling",
    )

    # Contract 2: monthly rolling with no minimum term (flexible from start)
    c2 = Contract(
        id=2,
        title="Streaming",
        category="Entertainment",
        status=ContractStatus.active,
        amount=15.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 1, 1),
        billing_anchor_date=date(2026, 1, 1),
        initial_term_end_date=None,
        initial_term_months=0,
        renewal_type="monthly_rolling",
    )

    proj = fin_svc.calculate_cashflow_projection([c1, c2], "EUR", as_of=date(2026, 1, 1), months=12)
    assert len(proj) == 12

    # Month 0 (2026-01):
    # c1 is committed (50.0), c2 is flexible (15.0) -> total 65.0
    assert proj[0]["month"] == "2026-01"
    assert proj[0]["amount"] == 65.0
    assert proj[0]["committed_amount"] == 50.0
    assert proj[0]["flexible_amount"] == 15.0
    assert len(proj[0]["contract_items"]) == 2

    # Month 5 (2026-06):
    # c1 (2026-06-01 <= 2026-06-30) still committed, c2 flexible
    assert proj[5]["month"] == "2026-06"
    assert proj[5]["committed_amount"] == 50.0
    assert proj[5]["flexible_amount"] == 15.0

    # Month 6 (2026-07):
    # c1 is now past initial_term_end_date (2026-07-01 > 2026-06-30) -> c1 is now flexible!
    # c1 (50.0) + c2 (15.0) = 65.0 flexible, 0.0 committed!
    assert proj[6]["month"] == "2026-07"
    assert proj[6]["committed_amount"] == 0.0
    assert proj[6]["flexible_amount"] == 65.0
    assert proj[6]["amount"] == 65.0


def test_cashflow_includes_cancelled_contract_until_termination():
    """Contracts with pending_cancellation or cancellation_confirmed are projected as committed until confirmed_end_date."""
    fin_svc = FinancialService()

    # Contract confirmed cancelled to 2026-03-31
    c_cancelled = Contract(
        id=3,
        title="Old Mobile Contract",
        category="Mobile",
        status=ContractStatus.cancellation_confirmed,
        amount=30.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2024, 1, 1),
        billing_anchor_date=date(2026, 1, 1),
        confirmed_end_date=date(2026, 3, 31),
    )

    proj = fin_svc.calculate_cashflow_projection([c_cancelled], "EUR", as_of=date(2026, 1, 1), months=6)
    assert len(proj) == 6

    # Months 0, 1, 2 (Jan, Feb, Mar 2026): active payments, counted as committed
    assert proj[0]["amount"] == 30.0
    assert proj[0]["committed_amount"] == 30.0
    assert proj[1]["amount"] == 30.0
    assert proj[2]["amount"] == 30.0

    # Month 3 (Apr 2026) and beyond: contract has ended, amount is 0
    assert proj[3]["amount"] == 0.0
    assert proj[4]["amount"] == 0.0


def test_due_dates_bidirectional_extrapolation_with_recent_anchor():
    """Verify that an anchor date in the recent past (e.g. from online banking) can extrapolate both
    historical past dates and future dates correctly without skipping."""
    fin_svc = FinancialService()

    # Old contract started 2020, user entered recent anchor date from Aug 2026
    c = Contract(
        status=ContractStatus.active,
        amount=29.99,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2020, 10, 25),
        billing_anchor_date=date(2026, 8, 28),
    )

    # Range covering both before and after anchor date (June 2026 to Dec 2026)
    due_dates = fin_svc._get_due_dates_in_range(c, date(2026, 6, 1), date(2026, 12, 31))
    assert due_dates == [
        date(2026, 6, 28),
        date(2026, 7, 28),
        date(2026, 8, 28),
        date(2026, 9, 28),
        date(2026, 10, 28),
        date(2026, 11, 28),
        date(2026, 12, 28),
    ]


def test_billing_anchor_fallback_to_start_date():
    """Verify that when billing_anchor_date is None, start_date is automatically used as the anchor."""
    fin_svc = FinancialService()

    c = Contract(
        id=99,
        title="Streaming No Anchor",
        category="Entertainment",
        status=ContractStatus.active,
        amount=12.99,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2020, 5, 15),
        billing_anchor_date=None,
    )

    # get_next_billing_date fallback
    next_bill = c.get_next_billing_date(as_of=date(2026, 9, 6))
    assert next_bill == date(2026, 9, 15)

    # _get_due_dates_in_range fallback
    due_dates = fin_svc._get_due_dates_in_range(c, date(2026, 9, 1), date(2026, 10, 31))
    assert due_dates == [date(2026, 9, 15), date(2026, 10, 15)]

    # Cashflow projection fallback
    proj = fin_svc.calculate_cashflow_projection([c], "EUR", as_of=date(2026, 9, 1), months=3)
    assert len(proj) == 3
    assert proj[0]["amount"] == 12.99
    assert proj[1]["amount"] == 12.99
    assert proj[2]["amount"] == 12.99


def test_cashflow_projection_scheduled_contract():
    """Verify that a future scheduled contract appears in cashflow projection only on/after start_date."""
    fin_svc = FinancialService()

    # Scheduled contract starting in March 2026, 50 EUR/mo, 6 months minimum term
    c_scheduled = Contract(
        id=101,
        title="Fiber Internet",
        category="Internet",
        status=ContractStatus.scheduled,
        amount=50.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 3, 1),
        billing_anchor_date=date(2026, 3, 1),
        initial_term_months=6,
        renewal_type="monthly_rolling",
    )

    proj = fin_svc.calculate_cashflow_projection([c_scheduled], "EUR", as_of=date(2026, 1, 1), months=12)
    assert len(proj) == 12

    # Jan & Feb 2026: contract not yet started -> 0 amount
    assert proj[0]["month"] == "2026-01"
    assert proj[0]["amount"] == 0.0
    assert len(proj[0]["contract_items"]) == 0

    assert proj[1]["month"] == "2026-02"
    assert proj[1]["amount"] == 0.0
    assert len(proj[1]["contract_items"]) == 0

    # March 2026: contract starts -> 50 EUR committed
    assert proj[2]["month"] == "2026-03"
    assert proj[2]["amount"] == 50.0
    assert proj[2]["committed_amount"] == 50.0
    assert proj[2]["flexible_amount"] == 0.0
    assert len(proj[2]["contract_items"]) == 1
    assert proj[2]["contract_items"][0]["contract_id"] == 101

    # Aug 2026: month 6 of initial term -> still committed
    # Start: 2026-03-01 + 6 months = 2026-09-01 (min_term_end)
    # Aug 2026 (index 7): d = 2026-08-01 <= 2026-09-01 -> committed
    assert proj[7]["month"] == "2026-08"
    assert proj[7]["amount"] == 50.0
    assert proj[7]["committed_amount"] == 50.0
    assert proj[7]["flexible_amount"] == 0.0

    # Sep 2026 (index 8): d = 2026-09-01 is not > min_term_end -> committed
    assert proj[8]["month"] == "2026-09"
    assert proj[8]["amount"] == 50.0
    assert proj[8]["committed_amount"] == 50.0
    assert proj[8]["flexible_amount"] == 0.0

    # Oct 2026 (index 9): d = 2026-10-01 > min_term_end -> flexible
    assert proj[9]["month"] == "2026-10"
    assert proj[9]["amount"] == 50.0
    assert proj[9]["committed_amount"] == 0.0
    assert proj[9]["flexible_amount"] == 50.0


def test_cashflow_projection_scheduled_fallback_anchor():
    """Verify that a scheduled contract without billing_anchor_date uses start_date."""
    fin_svc = FinancialService()

    c = Contract(
        id=102,
        title="Fitness Studio",
        status=ContractStatus.scheduled,
        amount=30.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 4, 15),
        billing_anchor_date=None,
    )

    proj = fin_svc.calculate_cashflow_projection([c], "EUR", as_of=date(2026, 1, 1), months=6)
    assert len(proj) == 6
    assert proj[0]["amount"] == 0.0  # Jan
    assert proj[1]["amount"] == 0.0  # Feb
    assert proj[2]["amount"] == 0.0  # Mar
    assert proj[3]["amount"] == 30.0  # Apr (2026-04-15 >= start_date)
    assert proj[4]["amount"] == 30.0  # May
    assert proj[5]["amount"] == 30.0  # Jun


def test_cashflow_projection_scheduled_mixed_with_active():
    """Verify combined cashflow projection with active and future scheduled contracts."""
    fin_svc = FinancialService()

    c_active = Contract(
        id=1,
        title="Active Gym",
        status=ContractStatus.active,
        amount=40.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2025, 1, 1),
        billing_anchor_date=date(2025, 1, 1),
    )
    c_scheduled = Contract(
        id=2,
        title="Upcoming Cloud VPS",
        status=ContractStatus.scheduled,
        amount=20.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 3, 1),
        billing_anchor_date=date(2026, 3, 1),
    )

    proj = fin_svc.calculate_cashflow_projection([c_active, c_scheduled], "EUR", as_of=date(2026, 1, 1), months=4)
    assert len(proj) == 4
    assert proj[0]["amount"] == 40.0  # Jan (only active)
    assert len(proj[0]["contract_items"]) == 1
    assert proj[1]["amount"] == 40.0  # Feb (only active)
    assert len(proj[1]["contract_items"]) == 1
    assert proj[2]["amount"] == 60.0  # Mar (both)
    assert len(proj[2]["contract_items"]) == 2
    assert proj[3]["amount"] == 60.0  # Apr (both)
    assert len(proj[3]["contract_items"]) == 2


def test_cashflow_projection_scheduled_beyond_horizon():
    """Verify that a scheduled contract starting beyond the projection horizon produces 0 due dates."""
    fin_svc = FinancialService()

    c_far_future = Contract(
        id=103,
        title="Far Future Lease",
        status=ContractStatus.scheduled,
        amount=500.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2028, 1, 1),
        billing_anchor_date=date(2028, 1, 1),
    )

    # In 2026 (12-month horizon), 2028 contract yields 0 amounts
    proj = fin_svc.calculate_cashflow_projection([c_far_future], "EUR", as_of=date(2026, 1, 1), months=12)
    assert len(proj) == 12
    assert all(b["amount"] == 0.0 for b in proj)
    assert all(len(b["contract_items"]) == 0 for b in proj)


def test_cashflow_projection_scheduled_archived_excluded():
    """Verify that an archived scheduled contract is strictly excluded."""
    fin_svc = FinancialService()

    c_archived = Contract(
        id=104,
        title="Archived Scheduled",
        status=ContractStatus.scheduled,
        is_archived=True,
        amount=100.0,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2026, 2, 1),
        billing_anchor_date=date(2026, 2, 1),
    )

    proj = fin_svc.calculate_cashflow_projection([c_archived], "EUR", as_of=date(2026, 1, 1), months=6)
    assert proj == []


def test_extended_contract_cost_summary_bounds_to_extension_period():
    """Ensure cost summary calculates initial_commitment strictly over the extension term."""
    fin_svc = FinancialService()

    # Contract started in 2020, extended for 24 months until 2028-09-28
    c = Contract(
        id=201,
        title="Extended Streaming",
        status=ContractStatus.active,
        amount=44.99,
        currency="EUR",
        frequency=Frequency.monthly,
        start_date=date(2020, 10, 25),
        billing_anchor_date=date(2020, 10, 25),
        initial_term_months=24,
        initial_term_end_date=date(2028, 9, 28),
        renewal_type="monthly_rolling",
    )
    # Price tiers: 24.99 during the 24m extension (2026-09-28 to 2028-09-27), 44.99 afterwards
    p_past = PriceEntry(contract_id=201, amount=30.0, currency="EUR", valid_from=date(2020, 10, 25), valid_to=date(2026, 9, 27))
    p_ext = PriceEntry(contract_id=201, amount=24.99, currency="EUR", valid_from=date(2026, 9, 28), valid_to=date(2028, 9, 27))
    p_future = PriceEntry(contract_id=201, amount=44.99, currency="EUR", valid_from=date(2028, 9, 28), valid_to=None)
    c.price_history = [p_past, p_ext, p_future]

    summary = fin_svc.calculate_contract_cost_summary(c, as_of=date(2026, 9, 1))

    init_comm = summary["initial_commitment"]
    assert init_comm is not None
    assert init_comm["months"] == 24
    assert init_comm["end_date"] == date(2028, 9, 28)
    assert init_comm["is_active"] is True
    assert init_comm["total_payments"] == 24
    # 24 * 24.99 = 599.76 EUR, NOT including past payments since 2020!
    assert init_comm["total_amount"] == 599.76





