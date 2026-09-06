import calendar
from datetime import date, timedelta
from app.models import Contract, ContractStatus, Frequency, PriceEntry, add_months, snap_to_target_period, calculate_next_billing_date
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
    """Check whether a contract is in force on the given date (respecting start_date & end_date)."""
    if getattr(contract, "is_archived", False):
        return False
    if contract.status not in (ContractStatus.active, ContractStatus.scheduled):
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

            # If anchor date is missing, fallback to start_date or normalized monthly cost if active
            anchor = contract.billing_anchor_date or contract.start_date
            if not anchor:
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

        eligible_statuses = (
            ContractStatus.active,
            ContractStatus.scheduled,
            ContractStatus.pending_cancellation,
            ContractStatus.cancellation_confirmed,
        )

        if not contracts or not any(
            c.status in eligible_statuses
            and not getattr(c, "is_archived", False)
            and (c.billing_anchor_date or c.start_date)
            for c in contracts
        ):
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
                "committed_amount": 0.0,
                "flexible_amount": 0.0,
                "contract_items": [],
            })

        if not buckets:
            return []

        horizon_start = buckets[0]["start"]
        horizon_end = buckets[-1]["end"]

        for contract in contracts:
            if getattr(contract, "is_archived", False):
                continue
            if contract.status not in eligible_statuses or not (contract.billing_anchor_date or contract.start_date):
                continue

            # Determine termination boundary if cancelled or fixed-term
            term_end_date = None
            if contract.status == ContractStatus.cancellation_confirmed:
                term_end_date = contract.confirmed_end_date or contract.end_date
            elif contract.status == ContractStatus.pending_cancellation:
                term_end_date = contract.confirmed_end_date or contract.earliest_cancellation_date or contract.end_date
            elif getattr(contract, 'renewal_type', None) == 'none':
                term_end_date = contract.end_date

            due_dates = self._get_due_dates_in_range(contract, horizon_start, horizon_end)
            for d in due_dates:
                # Discard payments beyond the termination date
                if term_end_date and d > term_end_date:
                    continue

                # Classify payment as flexible vs committed:
                # 1. Cancelled contracts are committed obligations until the confirmed termination date
                if contract.status in (ContractStatus.pending_cancellation, ContractStatus.cancellation_confirmed):
                    is_flexible = False
                # 2. Fixed-term contracts (renewal_type == 'none') terminate without rollover
                elif getattr(contract, 'renewal_type', None) == 'none':
                    is_flexible = False
                # 3. Fixed cycle renewals (fixed_period) cannot be cancelled monthly
                elif getattr(contract, 'renewal_type', None) == 'fixed_period':
                    is_flexible = False
                # 4. Standard monthly rolling consumer contracts:
                else:
                    min_term_end = contract.initial_term_end_date
                    if not min_term_end and contract.initial_term_months and contract.initial_term_months > 0:
                        c_start = contract.start_date or contract.billing_anchor_date
                        if c_start:
                            min_term_end = add_months(c_start, contract.initial_term_months)

                    if min_term_end:
                        is_flexible = d > min_term_end
                    else:
                        # No initial term obligation -> flexible from start
                        is_flexible = True

                # Find matching bucket
                d_key = d.strftime("%Y-%m")
                amt, curr = get_contract_price_on_date(contract, d)
                converted = self.currency_service.convert(amt, curr, target_currency)

                for b in buckets:
                    if b["month"] == d_key:
                        b["amount"] += converted
                        if is_flexible:
                            b["flexible_amount"] += converted
                        else:
                            b["committed_amount"] += converted

                        contract_title = contract.title or (contract.provider.name if contract.provider else contract.category)
                        b["contract_items"].append({
                            "contract_id": contract.id,
                            "title": contract_title,
                            "provider_name": contract.provider.name if contract.provider else "",
                            "category": contract.category,
                            "amount": round(converted, 2),
                            "is_flexible": is_flexible,
                        })
                        break

        return [
            {
                "month": b["month"],
                "label": b["label"],
                "amount": round(b["amount"], 2),
                "committed_amount": round(b["committed_amount"], 2),
                "flexible_amount": round(b["flexible_amount"], 2),
                "contract_items": b["contract_items"],
            }
            for b in buckets
        ]

    def _get_due_dates_in_range(
        self,
        contract: Contract,
        range_start: date,
        range_end: date,
        override_anchor: date | None = None,
    ) -> list[date]:
        """Extrapolate exact billing dates for a contract falling within [range_start, range_end].
        Supports bidirectional extrapolation from any past or future anchor in the cycle.
        """
        anchor = override_anchor or contract.billing_anchor_date or contract.start_date
        if not anchor:
            return []

        freq = contract.frequency
        due_dates = []

        # Weekly or biweekly
        if freq in (Frequency.weekly, Frequency.biweekly):
            step_days = 7 if freq == Frequency.weekly else 14
            diff_days = (range_start - anchor).days
            step_idx = (diff_days // step_days) - 1
            candidate = anchor + timedelta(days=step_idx * step_days)
            while candidate <= range_end:
                if candidate >= range_start:
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

            # Bidirectional step alignment: works seamlessly whether anchor is in the past, present, or future
            month_diff = (range_start.year - anchor.year) * 12 + (range_start.month - anchor.month)
            step_idx = (month_diff // step_months) - 1

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
            if contract.status != ContractStatus.active:
                continue

            # Fixed-term contracts terminate automatically and require no cancellation
            if getattr(contract, "renewal_type", None) == "none":
                continue

            deadline = None
            if hasattr(contract, "get_cancellation_deadline"):
                deadline = contract.get_cancellation_deadline(as_of=as_of_date)

            if deadline is None and contract.end_date:
                notice_amt = contract.cancellation_notice_amount or 0
                unit = (contract.cancellation_notice_unit or "days").lower()

                if unit == "months":
                    deadline = add_months(contract.end_date, -notice_amt)
                elif unit == "weeks":
                    deadline = contract.end_date - timedelta(weeks=notice_amt)
                else:
                    deadline = contract.end_date - timedelta(days=notice_amt)

            if not deadline:
                continue

            # Contracts that are monthly rolling without lock-in are not urgent
            if getattr(contract, "is_monthly_flexible", False):
                continue

            # Critical if contract hasn't ended and deadline is due within horizon_days (or already passed)
            effective_end = contract.end_date or getattr(contract, "earliest_cancellation_date", None)
            if (not effective_end or effective_end >= as_of_date) and deadline <= as_of_date + timedelta(days=horizon_days):
                critical.append(contract)

        return sorted(critical, key=lambda c: getattr(c, "cancellation_deadline", None) or c.end_date or date.max)

    def get_missing_notice(self, contracts: list[Contract]) -> list[Contract]:
        """Identify active contracts missing cancellation notice terms, excluding fixed-term contracts."""
        return [
            c
            for c in contracts
            if c.status == ContractStatus.active
            and getattr(c, "renewal_type", None) != "none"
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
            due_dates = self._get_due_dates_in_range(contract, calc_start, contract.end_date, override_anchor=anchor)
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
            due_dates = (
                self._get_due_dates_in_range(contract, calc_start, ref_date, override_anchor=anchor)
                if calc_start <= ref_date
                else []
            )
            paid_amount = 0.0

            for d in due_dates:
                amt, _ = get_contract_price_on_date(contract, d)
                paid_amount += amt

            # Forward 12-month cashflow projection accounting for future price adjustments
            one_year_ahead = ref_date + timedelta(days=365)
            upcoming_due_dates = self._get_due_dates_in_range(
                contract, ref_date + timedelta(days=1), one_year_ahead, override_anchor=anchor
            )

            if upcoming_due_dates:
                annual_amount = sum(get_contract_price_on_date(contract, d)[0] for d in upcoming_due_dates)
            else:
                eff_amt, _ = get_contract_price_on_date(contract, ref_date)
                annual_amount = normalize_to_monthly(eff_amt, contract.frequency) * 12.0

            initial_commitment = None
            has_term = bool(contract.initial_term_end_date or (contract.initial_term_months and contract.initial_term_months > 0))
            if has_term:
                target_period = getattr(contract, "cancellation_target_period", "exact") or "exact"
                if contract.initial_term_end_date:
                    initial_end = snap_to_target_period(contract.initial_term_end_date, target_period)
                    m_diff = (initial_end.year - calc_start.year) * 12 + (initial_end.month - calc_start.month)
                    term_months = contract.initial_term_months or max(1, m_diff)
                else:
                    initial_end = snap_to_target_period(add_months(calc_start, contract.initial_term_months), target_period)
                    term_months = contract.initial_term_months

                term_start = add_months(initial_end, -term_months)
                if term_start < calc_start:
                    term_start = calc_start

                range_end = initial_end - timedelta(days=1) if initial_end > term_start else initial_end
                initial_due_dates = self._get_due_dates_in_range(
                    contract, term_start, range_end, override_anchor=anchor
                )
                initial_total = sum(get_contract_price_on_date(contract, d)[0] for d in initial_due_dates)
                is_active = ref_date < initial_end
                initial_commitment = {
                    "months": term_months,
                    "end_date": initial_end,
                    "total_amount": round(initial_total, 2),
                    "currency": curr,
                    "total_payments": len(initial_due_dates),
                    "is_active": is_active,
                    "renewal_type": contract.renewal_type or "monthly_rolling",
                    "renewal_period_months": contract.renewal_period_months or 1,
                }

            # If contract has past initial commitment but a fixed follow-up period (fixed_period)
            current_period_commitment = None
            if getattr(contract, "renewal_type", None) == "fixed_period" and (
                not initial_commitment or not initial_commitment["is_active"]
            ):
                period_months = contract.renewal_period_months or 12
                earliest_cancel = None
                if hasattr(contract, "get_earliest_cancellation_date"):
                    earliest_cancel = contract.get_earliest_cancellation_date(as_of=ref_date)
                elif hasattr(contract, "earliest_cancellation_date"):
                    earliest_cancel = contract.earliest_cancellation_date

                if earliest_cancel and earliest_cancel >= ref_date:
                    period_start = add_months(earliest_cancel, -period_months)
                    if period_start < calc_start:
                        period_start = calc_start
                    period_due_dates = self._get_due_dates_in_range(
                        contract, period_start, earliest_cancel, override_anchor=anchor
                    )
                    period_total = sum(get_contract_price_on_date(contract, d)[0] for d in period_due_dates)
                    if not period_total:
                        eff_amt, _ = get_contract_price_on_date(contract, ref_date)
                        period_total = normalize_to_monthly(eff_amt, contract.frequency) * period_months

                    current_period_commitment = {
                        "bound_until": earliest_cancel,
                        "months": period_months,
                        "total_amount": round(period_total, 2),
                        "currency": curr,
                        "initial_months": initial_commitment["months"] if initial_commitment else 0,
                        "initial_end_date": initial_commitment["end_date"] if initial_commitment else None,
                    }

            return {
                "is_fixed_term": False,
                "currency": curr,
                "paid_amount": round(paid_amount, 2),
                "annual_amount": round(annual_amount, 2),
                "paid_payments": len(due_dates),
                "initial_commitment": initial_commitment,
                "current_period_commitment": current_period_commitment,
            }

    def calculate_provider_summary(
        self,
        contracts: list[Contract],
        target_currency: str = "EUR",
        as_of: date | None = None,
    ) -> dict:
        """
        Calculate aggregated financial and contract statistics for a specific provider.
        Normalizes amounts to the target currency.
        """
        as_of_date = as_of or date.today()
        total_contracts = len(contracts)
        active_contracts = [c for c in contracts if c.status == ContractStatus.active]
        canceled_contracts = [c for c in contracts if c.status == ContractStatus.canceled]
        archived_contracts = [c for c in contracts if getattr(c, "is_archived", False) or c.status == ContractStatus.archived]

        monthly_spend = self.calculate_monthly_budget(active_contracts, target_currency, as_of_date)
        annual_projected = round(monthly_spend * 12.0, 2)

        total_paid = 0.0
        total_remaining = 0.0
        has_fixed_term = False

        for c in contracts:
            c_summary = self.calculate_contract_cost_summary(c, as_of_date)
            c_curr = c_summary.get("currency", c.currency or "EUR")
            paid_val = c_summary.get("paid_amount", 0.0)
            paid_conv = self.currency_service.convert(paid_val, c_curr, target_currency)
            total_paid += paid_conv

            if c_summary.get("is_fixed_term"):
                has_fixed_term = True
                rem_val = c_summary.get("remaining_amount", 0.0)
                rem_conv = self.currency_service.convert(rem_val, c_curr, target_currency)
                total_remaining += rem_conv

        total_paid = round(total_paid, 2)
        total_remaining = round(total_remaining, 2) if has_fixed_term else None
        total_cost = round(total_paid + (total_remaining or 0.0), 2)

        return {
            "target_currency": target_currency,
            "total_contracts": total_contracts,
            "active_count": len(active_contracts),
            "canceled_count": len(canceled_contracts),
            "archived_count": len(archived_contracts),
            "monthly_spend": monthly_spend,
            "annual_projected": annual_projected,
            "total_paid": total_paid,
            "total_remaining": total_remaining,
            "total_cost": total_cost,
            "has_fixed_term": has_fixed_term,
        }

    def get_contract_price_timeline_chart(self, contract: Contract) -> dict:
        """
        Generate structured timeline chart data for contract price adjustments.
        Returns labels, values, point metadata, and summary statistics for Chart.js visualization.
        """
        currency = contract.currency or "EUR"

        # Collect and sort price history entries ascending by valid_from
        entries = sorted(contract.price_history or [], key=lambda p: p.valid_from)

        if not entries:
            # Fallback when no explicit price entries exist
            start_d = contract.start_date or date.today()
            amt = float(contract.amount or 0.0)
            return {
                "currency": currency,
                "labels": [start_d.strftime("%d.%m.%Y")],
                "amounts": [amt],
                "point_statuses": ["current"],
                "notes": [""],
                "has_multiple": False,
                "has_future": False,
                "stats": {
                    "initial_amount": amt,
                    "initial_date": start_d.strftime("%d.%m.%Y"),
                    "current_amount": amt,
                    "min_amount": amt,
                    "max_amount": amt,
                    "change_since_start_amount": 0.0,
                    "change_since_start_percent": 0.0,
                    "is_increase": False,
                    "is_reduction": False,
                },
            }

        today = date.today()
        timeline_points: list[dict] = []

        for i, p in enumerate(entries):
            timeline_points.append({
                "date": p.valid_from,
                "amount": round(float(p.amount), 2),
                "status": p.status,
                "note": p.note or "",
                "is_today": p.valid_from == today,
            })

            # Check if we should insert/append an endpoint for today or contract end
            is_current_entry = (p.status == "current") or (
                p.valid_from <= today and (p.valid_to is None or p.valid_to >= today)
            )
            has_next = (i + 1 < len(entries))

            if is_current_entry and p.valid_from < today:
                if has_next:
                    next_p = entries[i + 1]
                    if next_p.valid_from > today:
                        timeline_points.append({
                            "date": today,
                            "amount": round(float(p.amount), 2),
                            "status": "current",
                            "note": "",
                            "is_today": True,
                        })
                else:
                    # Last entry: extend to contract.end_date if terminated in the past, else to today
                    if (
                        contract.end_date
                        and contract.end_date < today
                        and contract.status in (ContractStatus.canceled, ContractStatus.cancellation_confirmed)
                    ):
                        if contract.end_date > p.valid_from:
                            timeline_points.append({
                                "date": contract.end_date,
                                "amount": round(float(p.amount), 2),
                                "status": "past",
                                "note": "",
                                "is_today": False,
                            })
                    else:
                        timeline_points.append({
                            "date": today,
                            "amount": round(float(p.amount), 2),
                            "status": "current",
                            "note": "",
                            "is_today": True,
                        })

        labels = [pt["date"].strftime("%d.%m.%Y") for pt in timeline_points]
        amounts = [pt["amount"] for pt in timeline_points]
        point_statuses = [pt["status"] for pt in timeline_points]
        notes = [pt["note"] for pt in timeline_points]
        is_today = [pt["is_today"] for pt in timeline_points]

        initial_entry = entries[0]
        initial_amount = round(float(initial_entry.amount), 2)
        initial_date = initial_entry.valid_from.strftime("%d.%m.%Y")
        current_amount = round(contract.current_amount, 2)
        min_amount = min(amounts)
        max_amount = max(amounts)

        diff_start = round(current_amount - initial_amount, 2)
        pct_start = round((diff_start / initial_amount) * 100, 1) if initial_amount > 0 else 0.0

        return {
            "currency": currency,
            "labels": labels,
            "amounts": amounts,
            "point_statuses": point_statuses,
            "notes": notes,
            "is_today": is_today,
            "has_multiple": len(entries) > 1,
            "has_future": any(p == "future" for p in point_statuses),
            "stats": {
                "initial_amount": initial_amount,
                "initial_date": initial_date,
                "current_amount": current_amount,
                "min_amount": min_amount,
                "max_amount": max_amount,
                "change_since_start_amount": diff_start,
                "change_since_start_percent": pct_start,
                "is_increase": diff_start > 0,
                "is_reduction": diff_start < 0,
            },
        }



