from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest
import requests
from sqlalchemy.exc import IntegrityError

from werkzeug.security import generate_password_hash
from app import db
from app.models import ExchangeRateCache, Contract, User, Frequency, ContractStatus
from app.services.currency_service import CurrencyService
from app.services.financial_service import FinancialService


def test_rate_date_unified_caching(app, mocker):
    """Test that historical rates (past dates) are cached indefinitely (Write Once, Read Forever)."""
    with app.app_context():
        past_date = date(2023, 5, 10)
        # Entry in cache with past date and last_updated 30 days ago
        old_time = datetime.now(timezone.utc) - timedelta(days=30)
        cache_entry = ExchangeRateCache(
            base_currency="USD",
            target_currency="EUR",
            rate=0.9125,
            rate_date=past_date,
            last_updated=old_time,
        )
        db.session.add(cache_entry)
        db.session.commit()

        mock_get = mocker.patch("requests.get")

        svc = CurrencyService()
        # Querying with as_of=past_date should hit the cache even if last_updated is 30 days old
        rate = svc.get_rate("USD", "EUR", as_of=past_date)
        assert rate == 0.9125
        mock_get.assert_not_called()


def test_convert_with_as_of_date(app, mocker):
    """Test convert() with a specific historical as_of date invokes Frankfurter v2 rates endpoint."""
    with app.app_context():
        hist_date = date(2024, 2, 1)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Frankfurter v2 returns rate list or dict
        mock_resp.json.return_value = [{"date": "2024-02-01", "rate": 0.925}]
        mock_get = mocker.patch("requests.get", return_value=mock_resp)

        svc = CurrencyService()
        converted = svc.convert(100.0, "USD", "EUR", as_of=hist_date)
        assert converted == 92.5
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        assert "date=2024-02-01" in call_url
        assert "base=USD" in call_url
        assert "quotes=EUR" in call_url

        # Check that it got saved in DB with rate_date=2024-02-01
        cached = ExchangeRateCache.query.filter_by(
            base_currency="USD", target_currency="EUR", rate_date=hist_date
        ).first()
        assert cached is not None
        assert cached.rate == 0.925


def test_unique_constraint_pair_date(app):
    """Test that UniqueConstraint on (base_currency, target_currency, rate_date) prevents duplicates."""
    with app.app_context():
        today = date.today()
        c1 = ExchangeRateCache(
            base_currency="GBP", target_currency="EUR", rate=1.18, rate_date=today
        )
        db.session.add(c1)
        db.session.commit()

        c2 = ExchangeRateCache(
            base_currency="GBP", target_currency="EUR", rate=1.19, rate_date=today
        )
        db.session.add(c2)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_weekly_billing_with_tag_exact_exchange_rates(app, mocker):
    """Test that Cashflow projection uses tag-exact exchange rates for weekly billings."""
    with app.app_context():
        # Create a test user with EUR currency
        user = User(
            username="currency_user",
            currency="EUR",
            hashed_password=generate_password_hash("pass123"),
        )
        db.session.add(user)
        db.session.commit()

        # Contract with weekly billing in USD
        anchor = date(2026, 1, 5)  # Monday
        contract = Contract(
            user_id=user.id,
            title="US Weekly Sub",
            category="subscriptions",
            status=ContractStatus.active,
            amount=10.0,
            currency="USD",
            frequency=Frequency.weekly,
            billing_anchor_date=anchor,
            start_date=anchor,
        )
        db.session.add(contract)
        db.session.commit()

        # Track calls to convert()
        svc = CurrencyService()
        recorded_dates = []

        def mock_convert(amount, base, target, as_of=None):
            recorded_dates.append(as_of)
            return amount * 0.85

        mocker.patch.object(svc, "convert", side_effect=mock_convert)

        fin_svc = FinancialService(currency_service=svc)
        projection = fin_svc.calculate_cashflow_projection(
            contracts=[contract],
            target_currency="EUR",
            months=3,
        )

        assert len(projection) == 3
        # Should have recorded multiple calls to convert with distinct dates
        assert len(recorded_dates) > 0
        for d in recorded_dates:
            assert isinstance(d, date)


def test_api_currency_rate_endpoint(client, app, mocker):
    """Test /contracts/api/currency/rate endpoint authentication and rate calculation."""
    # 1. Unauthenticated request should redirect to login
    resp = client.get("/contracts/api/currency/rate?from=USD&to=EUR")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]

    # Create user and log in
    with app.app_context():
        user = User(
            username="api_curr_user",
            currency="EUR",
            hashed_password=generate_password_hash("pass123"),
        )
        db.session.add(user)
        db.session.commit()

    client.post("/login", data={"username": "api_curr_user", "password": "pass123"}, follow_redirects=True)

    # 2. Authenticated request with invalid params
    resp = client.get("/contracts/api/currency/rate")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False

    # 3. Same currency returns 1.0 immediately
    resp = client.get("/contracts/api/currency/rate?from=EUR&to=EUR")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["rate"] == 1.0

    # 4. Valid foreign conversion returns rate and formatted date
    with app.app_context():
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"date": "2026-09-04", "base": "USD", "quote": "EUR", "rate": 0.8606}
        mocker.patch("requests.get", return_value=mock_resp)

        resp = client.get("/contracts/api/currency/rate?from=USD&to=EUR")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["rate"] == 0.8606
        assert data["from"] == "USD"
        assert data["to"] == "EUR"
        assert "date" in data
