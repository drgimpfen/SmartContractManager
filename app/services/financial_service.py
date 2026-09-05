import calendar
from datetime import date, timedelta
from app.models import Contract, ContractStatus, Frequency, PriceEntry, add_months, calculate_next_billing_date
from app.services.currency_service import CurrencyService


def normalize_to_monthly(amount: float, frequency: Frequency | str) -> float:
    """Normalize a payment amount to an average monthly cost."""
    if not amount:
        return 0.0

    freq_val = frequency.value if isinstance(frequency, Frequency) else str(frequency).lower()

    if freq_val == "weekly":
        return (amount * 52.0) / 12.0
    elif freq_val == "biweekly":
        return (amount * 26.0) / 12.0
    elif freq_val == "monthly":
        return float(amount)
    elif freq_val == "quarterly":
        return amount / 3.0
    elif freq_val == "yearly":
        return amount / 12.0
    return float(amount)


def get_contract_price_on_date(contract: Contract, on_date: date) -> tuple[float, str]:
    """
    Get the effective amount and currency for a contract on a specific date.
    Checks PriceEntry history first, falling back to contract amount and currency.
    """
    if contract.price_history:
        for p in contract.price_history:
            if p.valid_from <= on_date and (p.valid_to is None or p.valid_to >= on_date):
                return float(p.amount), p.currency

    return float(contract.amount or 0.0), (contract.currency or "EUR")


def is_contract_active_on_date(contract: Contract, check_date: date) -> bool:
    """Check whether an active contract is in force on the given date (respecting start_date & end_date)."""
    if contract.status != ContractStatus.active:
        return False
    if contract.start_date and contract.start_date > check_date:
        return False
    if contract.end_date and contract.end_date < check_date:
        return False
    return True


class FinancialService:
    """Service for deterministic financial calculations, cashflow projections, and budget analytics."""

    def __init__(self, currency_service: CurrencyService | None = None):
        self.currency_service = currency_service or CurrencyService()

    def calculate_monthly_budget(
        self,
        contracts: list[Contract],
        target_currency: str = "EUR",
        as_of: date | None = None,
    ) -> float:
        """
        Calculate smoothed average monthly budget across all active contracts in target_currency.
        Normalizes payment frequencies (weekly, quarterly, etc.) to a monthly equivalent.
        """
        as_of_date = as_of or date.today()
        total = 0.0

        for contract in contracts:
            if not is_contract_active_on_date(contract, as_of_date):
                continue

            amt, curr = get_contract_price_on_date(contract, as_of_date)
            converted = self.currency_service.convert(amt, curr, target_currency)
            monthly = normalize_to_monthly(converted, contract.frequency)
            total += monthly

        return round(total, 2)

    def calculate_annual_budget(
        self,
        contracts: list[Contract],
        target_currency: str = "EUR",
        as_of: date | None = None,
    ) -> float:
        """Calculate annualized total budget (monthly_budget * 12)."""
        monthly = self.calculate_monthly_budget(contracts, target_currency, as_of)
        return round(monthly * 12.0, 2)

    def calculate_current_month_expenses(
        self,
        contracts: list[Contract],
        target_currency: str = "EUR",
        as_of: date | None = None,
    ) -> float:
        """
        Calculate the sum of actual bills due in the current calendar month.
        Reflects real cash outflows in the current month rather than smoothed average.
        """
        as_of_date = as_of or date.today()
        m_start = date(as_of_date.year, as_of_date.month, 1)
        last_day = calendar.monthrange(as_of_date.year, as_of_date.month)[1]
        m_end = date(as_of_date.year, as_of_date.month, last_day)

        total = 0.0

        for contract in contracts:
            if contract.status != ContractStatus.active:
                continue

            # If anchor date is missing, fallback to normalized monthly cost if active
            if not contract.billing_anchor_date:
                if is_contract_active_on_date(contract, as_of_date):
                    amt, curr = get_contract_price_on_date(contract, as_of_date)
                    converted = self.currency_service.convert(amt, curr, target_currency)
                    total += normalize_to_monthly(converted, contract.frequency)
                continue

            # Determine due dates in current month
            due_dates = self._get_due_dates_in_range(contract, m_start, m_end)
            for d in due_dates:
                amt, curr = get_contract_price_on_date(contract, d)
                converted = self.currency_service.convert(amt, curr, target_currency)
                total += converted

        return round(total, 2)

    def calculate_cashflow_projection(
        self,
        contracts: list[Contract],
        target_currency: str = "EUR",
        as_of: date | None = None,
        months: int = 12,
    ) -> list[dict]:
        """
        Calculate a 12-month forward cashflow projection of actual due amounts.
        Returns a list of dicts: [{'month': 'YYYY-MM', 'label': 'Mmm YYYY', 'amount': float}, ...]
        """
        as_of_date = as_of or date.today()

        if not contracts or not any(c.status == ContractStatus.active and c.billing_anchor_date for c in contracts):
            return []

        base_first_of_month = date(as_of_date.year, as_of_date.month, 1)

        buckets = []
        for i in range(months):
            m_first = add_months(base_first_of_month, i)
            days_in_m = calendar.monthrange(m_first.year, m_first.month)[1]
            m_last = date(m_first.year, m_first.month, days_in_m)
            buckets.append({
                "month": m_first.strftime("%Y-%m"),
                "label": m_first.strftime("%b %Y"),
                "start": m_first,
                "end": m_last,
                "amount": 0.0,
            })

        if not buckets:
            return []

        horizon_start = buckets[0]["start"]
        horizon_end = buckets[-1]["end"]

        for contract in contracts:
            if contract.status != ContractStatus.active or not contract.billing_anchor_date:
                continue

            due_dates = self._get_due_dates_in_range(contract, horizon_start, horizon_end)
            for d in due_dates:
                # Find matching bucket
                d_key = d.strftime("%Y-%m")
                amt, curr = get_contract_price_on_date(contract, d)
                converted = self.currency_service.convert(amt, curr, target_currency)

                for b in buckets:
                    if b["month"] == d_key:
                        b["amount"] += converted
                        break

        return [
            {
                "month": b["month"],
                "label": b["label"],
                "amount": round(b["amount"], 2),
            }
            for b in buckets
        ]

    def _get_due_dates_in_range(
        self, contract: Contract, range_start: date, range_end: date
    ) -> list[date]:
        """Extrapolate exact billing dates for a contract falling within [range_start, range_end]."""
        anchor = contract.billing_anchor_date
        if not anchor:
            return []

        freq = contract.frequency
        due_dates = []

        # Weekly or biweekly
        if freq in (Frequency.weekly, Frequency.biweekly):
            step_days = 7 if freq == Frequency.weekly else 14
            # Align first candidate on or after range_start
            candidate = calculate_next_billing_date(anchor, freq, range_start)
            while candidate <= range_end:
                if (not contract.start_date or candidate >= contract.start_date) and (
                    not contract.end_date or candidate <= contract.end_date
                ):
                    due_dates.append(candidate)
                elif contract.end_date and candidate > contract.end_date:
                    break
                candidate += timedelta(days=step_days)

        # Monthly, quarterly, yearly
        else:
            step_months = 1 if freq == Frequency.monthly else (3 if freq == Frequency.quarterly else 12)

            # Determine starting step
            if anchor < range_start:
                month_diff = (range_start.year - anchor.year) * 12 + (range_start.month - anchor.month)
                step_idx = max(0, (month_diff // step_months) - 1)
            else:
                step_idx = 0

            while True:
                candidate = add_months(anchor, step_idx * step_months)
                if candidate > range_end:
                    break

                if candidate >= range_start:
                    if (not contract.start_date or candidate >= contract.start_date) and (
                        not contract.end_date or candidate <= contract.end_date
                    ):
                        due_dates.append(candidate)
                    elif contract.end_date and candidate > contract.end_date:
                        break

                step_idx += 1

        return due_dates

    def calculate_category_distribution(
        self,
        contracts: list[Contract],
        target_currency: str = "EUR",
        as_of: date | None = None,
    ) -> list[dict]:
        """
        Calculate normalized monthly spend grouped by category in target_currency.
        Returns sorted list of dicts: [{'category': 'Internet', 'value': 49.99}, ...]
        """
        as_of_date = as_of or date.today()
        categories: dict[str, float] = {}

        for contract in contracts:
            if not is_contract_active_on_date(contract, as_of_date):
                continue

            cat = (contract.category or "Sonstiges").strip()
            amt, curr = get_contract_price_on_date(contract, as_of_date)
            converted = self.currency_service.convert(amt, curr, target_currency)
            monthly = normalize_to_monthly(converted, contract.frequency)

            categories[cat] = categories.get(cat, 0.0) + monthly

        result = [
            {"category": cat, "value": round(val, 2)}
            for cat, val in sorted(categories.items(), key=lambda item: item[1], reverse=True)
            if round(val, 2) > 0.0
        ]
        return result

    def get_critical_deadlines(
        self,
        contracts: list[Contract],
        as_of: date | None = None,
        horizon_days: int = 30,
    ) -> list[Contract]:
        """
        Identify active contracts whose cancellation notice deadline is approaching within horizon_days
        or has recently passed while contract is still active.
        """
        as_of_date = as_of or date.today()
        critical = []

        for contract in contracts:
            if contract.status != ContractStatus.active or not contract.end_date:
                continue

            notice_amt = contract.cancellation_notice_amount or 0
            unit = (contract.cancellation_notice_unit or "days").lower()

            if unit == "months":
                deadline = add_months(contract.end_date, -notice_amt)
            elif unit == "weeks":
                deadline = contract.end_date - timedelta(weeks=notice_amt)
            else:
                deadline = contract.end_date - timedelta(days=notice_amt)

            # Critical if contract hasn't ended and deadline is due within horizon_days (or already passed)
            if contract.end_date >= as_of_date and deadline <= as_of_date + timedelta(days=horizon_days):
                critical.append(contract)

        return sorted(critical, key=lambda c: c.end_date or date.max)

    def get_missing_notice(self, contracts: list[Contract]) -> list[Contract]:
        """Identify active contracts missing cancellation notice terms."""
        return [
            c
            for c in contracts
            if c.status == ContractStatus.active
            and (not c.cancellation_notice_amount or c.cancellation_notice_amount <= 0)
        ]

    def calculate_contract_cost_summary(
        self, contract: Contract, as_of: date | None = None
    ) -> dict:
        """
        Calculate total lifetime contract costs, breaking down into paid so far and remaining costs.
        For fixed-term contracts: calculates total, paid, and remaining across contract lifespan.
        For open-ended contracts: calculates total paid so far and projected annual cost.
        """
        ref_date = as_of or date.today()
        calc_start = contract.start_date or contract.billing_anchor_date or ref_date
        is_fixed = bool(contract.end_date and contract.end_date >= calc_start)

        curr = contract.currency or "EUR"

        if is_fixed:
            anchor = contract.billing_anchor_date or calc_start
            eff_contract = contract if contract.billing_anchor_date else Contract(
                billing_anchor_date=anchor,
                frequency=contract.frequency,
                start_date=contract.start_date,
                end_date=contract.end_date,
                amount=contract.amount,
                currency=contract.currency,
                price_history=contract.price_history,
                status=contract.status,
            )

            due_dates = self._get_due_dates_in_range(eff_contract, calc_start, contract.end_date)
            total_amount = 0.0
            paid_amount = 0.0
            remaining_amount = 0.0
            paid_payments = 0
            remaining_payments = 0

            for d in due_dates:
                amt, _ = get_contract_price_on_date(contract, d)
                total_amount += amt
                if d <= ref_date:
                    paid_amount += amt
                    paid_payments += 1
                else:
                    remaining_amount += amt
                    remaining_payments += 1

            return {
                "is_fixed_term": True,
                "currency": curr,
                "total_amount": round(total_amount, 2),
                "paid_amount": round(paid_amount, 2),
                "remaining_amount": round(remaining_amount, 2),
                "total_payments": len(due_dates),
                "paid_payments": paid_payments,
                "remaining_payments": remaining_payments,
            }
        else:
            anchor = contract.billing_anchor_date or calc_start
            eff_contract = contract if contract.billing_anchor_date else Contract(
                billing_anchor_date=anchor,
                frequency=contract.frequency,
                start_date=contract.start_date,
                amount=contract.amount,
                currency=contract.currency,
                price_history=contract.price_history,
                status=contract.status,
            )

            due_dates = self._get_due_dates_in_range(eff_contract, calc_start, ref_date) if calc_start <= ref_date else []
            paid_amount = 0.0

            for d in due_dates:
                amt, _ = get_contract_price_on_date(contract, d)
                paid_amount += amt

            annual_amount = normalize_to_monthly(contract.amount or 0.0, contract.frequency) * 12.0

            return {
                "is_fixed_term": False,
                "currency": curr,
                "paid_amount": round(paid_amount, 2),
                "annual_amount": round(annual_amount, 2),
                "paid_payments": len(due_dates),
            }

