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

