from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from typing import Optional


FREQUENCY_FACTORS = {
    "weekly": 52 / 12,
    "biweekly": 26 / 12,
    "monthly": 1.0,
    "quarterly": 1 / 3,
    "yearly": 1 / 12,
}


def to_local_time(value: datetime, timezone: str) -> datetime:
    if value is None:
        return None
    tz = ZoneInfo(timezone)
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("UTC"))
    return value.astimezone(tz)


def format_date(value: Optional[date], timezone: str = "Europe/Berlin") -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d")


def normalize_monthly_amount(amount: float, frequency: str) -> float:
    return round(amount * FREQUENCY_FACTORS.get(frequency, 1.0), 2)


def parse_notice_amount(amount: int, unit: str) -> timedelta:
    if not amount or amount <= 0:
        return timedelta(days=0)
    if unit == "weeks":
        return timedelta(weeks=amount)
    if unit == "months":
        return timedelta(days=30 * amount)
    return timedelta(days=amount)


def build_monthly_projection(contracts, months=12):
    now = datetime.utcnow().date()
    projection = []
    totals = {i: 0.0 for i in range(months)}
    for contract in contracts:
        if contract.status != "active" and contract.status != "ContractStatus.active":
            continue
        monthly_value = normalize_monthly_amount(contract.amount or 0.0, contract.frequency.value if hasattr(contract.frequency, "value") else contract.frequency)
        for idx in range(months):
            totals[idx] += monthly_value
    for idx in range(months):
        month = (now.replace(day=1) + timedelta(days=31 * idx)).replace(day=1)
        projection.append({"month": month.strftime("%Y-%m"), "total": round(totals[idx], 2)})
    return projection
