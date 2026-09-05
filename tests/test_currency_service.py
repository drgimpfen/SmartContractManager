from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest
import requests

from app import db
from app.models import ExchangeRateCache
from app.services.currency_service import CurrencyService


def test_same_currency(app):
    with app.app_context():
        svc = CurrencyService()
        rate = svc.get_rate("EUR", "EUR")
        assert rate == 1.0
        # Case insensitivity
        assert svc.get_rate("usd", "USD") == 1.0


def test_cache_miss_calls_api_and_saves(app, mocker):
    with app.app_context():
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rates": {"EUR": 0.854}}
        mock_get = mocker.patch("requests.get", return_value=mock_resp)

        svc = CurrencyService()
        rate = svc.get_rate("USD", "EUR")

        assert rate == 0.854
        mock_get.assert_called_once()

        # Verify saved in DB
        cached = ExchangeRateCache.query.filter_by(base_currency="USD", target_currency="EUR").first()
        assert cached is not None
        assert cached.rate == 0.854


def test_cache_hit_within_24h_does_not_call_api(app, mocker):
    with app.app_context():
        recent_time = datetime.now(timezone.utc) - timedelta(hours=3)
        cache_entry = ExchangeRateCache(
            base_currency="GBP", target_currency="EUR", rate=1.17, last_updated=recent_time
        )
        db.session.add(cache_entry)
        db.session.commit()

        mock_get = mocker.patch("requests.get")

        svc = CurrencyService()
        rate = svc.get_rate("GBP", "EUR")

        assert rate == 1.17
        mock_get.assert_not_called()


def test_cache_expired_calls_api_and_updates(app, mocker):
    with app.app_context():
        stale_time = datetime.now(timezone.utc) - timedelta(hours=25)
        cache_entry = ExchangeRateCache(
            base_currency="CHF", target_currency="EUR", rate=1.02, last_updated=stale_time
        )
        db.session.add(cache_entry)
        db.session.commit()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rates": {"EUR": 1.05}}
        mock_get = mocker.patch("requests.get", return_value=mock_resp)

        svc = CurrencyService()
        rate = svc.get_rate("CHF", "EUR")

        assert rate == 1.05
        mock_get.assert_called_once()

        # DB updated
        updated = ExchangeRateCache.query.filter_by(base_currency="CHF", target_currency="EUR").first()
        assert updated.rate == 1.05


def test_api_error_fallback_to_stale_cache(app, mocker):
    with app.app_context():
        stale_time = datetime.now(timezone.utc) - timedelta(days=2)
        cache_entry = ExchangeRateCache(
            base_currency="JPY", target_currency="EUR", rate=0.0062, last_updated=stale_time
        )
        db.session.add(cache_entry)
        db.session.commit()

        mocker.patch("requests.get", side_effect=requests.RequestException("Connection timeout"))

        svc = CurrencyService()
        rate = svc.get_rate("JPY", "EUR")

        assert rate == 0.0062


def test_api_error_no_cache_fallback_1_0(app, mocker):
    with app.app_context():
        mocker.patch("requests.get", side_effect=requests.RequestException("Connection failed"))

        svc = CurrencyService()
        rate = svc.get_rate("CAD", "EUR")

        assert rate == 1.0


def test_convert_calculations(app, mocker):
    with app.app_context():
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rates": {"EUR": 0.85}}
        mocker.patch("requests.get", return_value=mock_resp)

        svc = CurrencyService()
        assert svc.convert(100.0, "USD", "EUR") == 85.0
        assert svc.convert(0.0, "USD", "EUR") == 0.0
        assert svc.convert(None, "USD", "EUR") == 0.0
