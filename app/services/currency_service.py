import logging
from datetime import datetime, timedelta, timezone
import requests

from app import db
from app.models import ExchangeRateCache

logger = logging.getLogger(__name__)


class CurrencyService:
    """Service for retrieving foreign exchange rates with a 24-hour database cache."""

    API_BASE_URL = "https://api.frankfurter.dev/v1/latest"
    CACHE_DURATION = timedelta(hours=24)

    def __init__(self, api_url: str | None = None):
        self.api_url = api_url or self.API_BASE_URL

    def get_rate(self, base_currency: str, target_currency: str) -> float:
        """
        Get exchange rate from base_currency to target_currency.
        Returns 1.0 if both currencies are identical.
        Uses cached rate if updated within last 24 hours.
        Otherwise fetches rate from Frankfurter API and updates DB cache.
        Falls back to stale cache or 1.0 on failure.
        """
        base = (base_currency or "EUR").strip().upper()
        target = (target_currency or "EUR").strip().upper()

        if base == target:
            return 1.0

        now = datetime.now(timezone.utc)
        cached = ExchangeRateCache.query.filter_by(
            base_currency=base, target_currency=target
        ).first()

        if cached and cached.last_updated:
            last_updated = cached.last_updated
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)

            if now - last_updated < self.CACHE_DURATION:
                return cached.rate

        # Fetch from API
        try:
            url = f"{self.api_url}?base={base}&symbols={target}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                rate_val = float(data["rates"][target])

                if cached:
                    cached.rate = rate_val
                    cached.last_updated = now
                else:
                    cached = ExchangeRateCache(
                        base_currency=base,
                        target_currency=target,
                        rate=rate_val,
                        last_updated=now,
                    )
                    db.session.add(cached)

                db.session.commit()
                return rate_val
            else:
                logger.warning(
                    f"Frankfurter API returned status {resp.status_code} for {base}->{target}: {resp.text}"
                )
        except Exception as e:
            logger.warning(
                f"Failed to fetch exchange rate {base}->{target} from API: {e}"
            )

        # Fallback to existing stale cache or default to 1.0
        if cached:
            return cached.rate

        return 1.0

    def convert(self, amount: float, from_currency: str, to_currency: str) -> float:
        """Convert amount from from_currency to to_currency, rounded to 2 decimal places."""
        if not amount:
            return 0.0
        rate = self.get_rate(from_currency, to_currency)
        return round(amount * rate, 2)
