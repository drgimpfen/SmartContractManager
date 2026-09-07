import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
import requests

from app import db
from app.models import ExchangeRateCache

logger = logging.getLogger(__name__)

TOP_CURRENCIES: list[tuple[str, str]] = [
    ("EUR", "Euro (EUR)"),
    ("USD", "US Dollar (USD)"),
    ("CHF", "Schweizer Franken (CHF)"),
    ("GBP", "Britisches Pfund (GBP)"),
    ("PLN", "Polnischer Złoty (PLN)"),
]

# Canonical 165 world currencies supported by Frankfurter API v2
ALL_CURRENCIES: list[tuple[str, str]] = [
    ('AED', 'United Arab Emirates Dirham (AED)'),
    ('AFN', 'Afghan Afghani (AFN)'),
    ('ALL', 'Albanian Lek (ALL)'),
    ('AMD', 'Armenian Dram (AMD)'),
    ('ANG', 'Netherlands Antillean Guilder (ANG)'),
    ('AOA', 'Angolan Kwanza (AOA)'),
    ('ARS', 'Argentine Peso (ARS)'),
    ('AUD', 'Australian Dollar (AUD)'),
    ('AWG', 'Aruban Florin (AWG)'),
    ('AZN', 'Azerbaijani Manat (AZN)'),
    ('BAM', 'Bosnia and Herzegovina Convertible Mark (BAM)'),
    ('BBD', 'Barbadian Dollar (BBD)'),
    ('BDT', 'Bangladeshi Taka (BDT)'),
    ('BHD', 'Bahraini Dinar (BHD)'),
    ('BIF', 'Burundian Franc (BIF)'),
    ('BMD', 'Bermudian Dollar (BMD)'),
    ('BND', 'Brunei Dollar (BND)'),
    ('BOB', 'Bolivian Boliviano (BOB)'),
    ('BRL', 'Brazilian Real (BRL)'),
    ('BSD', 'Bahamian Dollar (BSD)'),
    ('BTN', 'Bhutanese Ngultrum (BTN)'),
    ('BWP', 'Botswana Pula (BWP)'),
    ('BYN', 'Belarusian Ruble (BYN)'),
    ('BZD', 'Belize Dollar (BZD)'),
    ('CAD', 'Canadian Dollar (CAD)'),
    ('CDF', 'Congolese Franc (CDF)'),
    ('CHF', 'Swiss Franc (CHF)'),
    ('CLP', 'Chilean Peso (CLP)'),
    ('CNH', 'Chinese Renminbi Yuan Offshore (CNH)'),
    ('CNY', 'Chinese Renminbi Yuan (CNY)'),
    ('COP', 'Colombian Peso (COP)'),
    ('CRC', 'Costa Rican Colón (CRC)'),
    ('CUP', 'Cuban Peso (CUP)'),
    ('CVE', 'Cape Verdean Escudo (CVE)'),
    ('CZK', 'Czech Koruna (CZK)'),
    ('DJF', 'Djiboutian Franc (DJF)'),
    ('DKK', 'Danish Krone (DKK)'),
    ('DOP', 'Dominican Peso (DOP)'),
    ('DZD', 'Algerian Dinar (DZD)'),
    ('EGP', 'Egyptian Pound (EGP)'),
    ('ERN', 'Eritrean Nakfa (ERN)'),
    ('ETB', 'Ethiopian Birr (ETB)'),
    ('EUR', 'Euro (EUR)'),
    ('FJD', 'Fijian Dollar (FJD)'),
    ('FKP', 'Falkland Pound (FKP)'),
    ('GBP', 'British Pound (GBP)'),
    ('GEL', 'Georgian Lari (GEL)'),
    ('GGP', 'Guernsey Pound (GGP)'),
    ('GHS', 'Ghanaian Cedi (GHS)'),
    ('GIP', 'Gibraltar Pound (GIP)'),
    ('GMD', 'Gambian Dalasi (GMD)'),
    ('GNF', 'Guinean Franc (GNF)'),
    ('GTQ', 'Guatemalan Quetzal (GTQ)'),
    ('GYD', 'Guyanese Dollar (GYD)'),
    ('HKD', 'Hong Kong Dollar (HKD)'),
    ('HNL', 'Honduran Lempira (HNL)'),
    ('HTG', 'Haitian Gourde (HTG)'),
    ('HUF', 'Hungarian Forint (HUF)'),
    ('IDR', 'Indonesian Rupiah (IDR)'),
    ('ILS', 'Israeli New Shekel (ILS)'),
    ('IMP', 'Isle of Man Pound (IMP)'),
    ('INR', 'Indian Rupee (INR)'),
    ('IQD', 'Iraqi Dinar (IQD)'),
    ('IRR', 'Iranian Rial (IRR)'),
    ('ISK', 'Icelandic Króna (ISK)'),
    ('JEP', 'Jersey Pound (JEP)'),
    ('JMD', 'Jamaican Dollar (JMD)'),
    ('JOD', 'Jordanian Dinar (JOD)'),
    ('JPY', 'Japanese Yen (JPY)'),
    ('KES', 'Kenyan Shilling (KES)'),
    ('KGS', 'Kyrgyzstani Som (KGS)'),
    ('KHR', 'Cambodian Riel (KHR)'),
    ('KMF', 'Comorian Franc (KMF)'),
    ('KPW', 'North Korean Won (KPW)'),
    ('KRW', 'South Korean Won (KRW)'),
    ('KWD', 'Kuwaiti Dinar (KWD)'),
    ('KYD', 'Cayman Islands Dollar (KYD)'),
    ('KZT', 'Kazakhstani Tenge (KZT)'),
    ('LAK', 'Lao Kip (LAK)'),
    ('LBP', 'Lebanese Pound (LBP)'),
    ('LKR', 'Sri Lankan Rupee (LKR)'),
    ('LRD', 'Liberian Dollar (LRD)'),
    ('LSL', 'Lesotho Loti (LSL)'),
    ('LYD', 'Libyan Dinar (LYD)'),
    ('MAD', 'Moroccan Dirham (MAD)'),
    ('MDL', 'Moldovan Leu (MDL)'),
    ('MGA', 'Malagasy Ariary (MGA)'),
    ('MKD', 'Macedonian Denar (MKD)'),
    ('MMK', 'Myanmar Kyat (MMK)'),
    ('MNT', 'Mongolian Tögrög (MNT)'),
    ('MOP', 'Macanese Pataca (MOP)'),
    ('MRO', 'Mauritanian Ouguiya (MRO)'),
    ('MRU', 'Mauritanian Ouguiya (MRU)'),
    ('MUR', 'Mauritian Rupee (MUR)'),
    ('MVR', 'Maldivian Rufiyaa (MVR)'),
    ('MWK', 'Malawian Kwacha (MWK)'),
    ('MXN', 'Mexican Peso (MXN)'),
    ('MYR', 'Malaysian Ringgit (MYR)'),
    ('MZN', 'Mozambican Metical (MZN)'),
    ('NAD', 'Namibian Dollar (NAD)'),
    ('NGN', 'Nigerian Naira (NGN)'),
    ('NIO', 'Nicaraguan Córdoba (NIO)'),
    ('NOK', 'Norwegian Krone (NOK)'),
    ('NPR', 'Nepalese Rupee (NPR)'),
    ('NZD', 'New Zealand Dollar (NZD)'),
    ('OMR', 'Omani Rial (OMR)'),
    ('PAB', 'Panamanian Balboa (PAB)'),
    ('PEN', 'Peruvian Sol (PEN)'),
    ('PGK', 'Papua New Guinean Kina (PGK)'),
    ('PHP', 'Philippine Peso (PHP)'),
    ('PKR', 'Pakistani Rupee (PKR)'),
    ('PLN', 'Polish Złoty (PLN)'),
    ('PYG', 'Paraguayan Guaraní (PYG)'),
    ('QAR', 'Qatari Riyal (QAR)'),
    ('RON', 'Romanian Leu (RON)'),
    ('RSD', 'Serbian Dinar (RSD)'),
    ('RUB', 'Russian Ruble (RUB)'),
    ('RWF', 'Rwandan Franc (RWF)'),
    ('SAR', 'Saudi Riyal (SAR)'),
    ('SBD', 'Solomon Islands Dollar (SBD)'),
    ('SCR', 'Seychellois Rupee (SCR)'),
    ('SDG', 'Sudanese Pound (SDG)'),
    ('SEK', 'Swedish Krona (SEK)'),
    ('SGD', 'Singapore Dollar (SGD)'),
    ('SHP', 'Saint Helenian Pound (SHP)'),
    ('SLE', 'New Leone (SLE)'),
    ('SOS', 'Somali Shilling (SOS)'),
    ('SRD', 'Surinamese Dollar (SRD)'),
    ('SSP', 'South Sudanese Pound (SSP)'),
    ('STN', 'São Tomé and Príncipe Second Dobra (STN)'),
    ('SVC', 'Salvadoran Colón (SVC)'),
    ('SYP', 'Syrian Pound (SYP)'),
    ('SZL', 'Swazi Lilangeni (SZL)'),
    ('THB', 'Thai Baht (THB)'),
    ('TJS', 'Tajikistani Somoni (TJS)'),
    ('TMT', 'Turkmenistani Manat (TMT)'),
    ('TND', 'Tunisian Dinar (TND)'),
    ('TOP', 'Tongan Paʻanga (TOP)'),
    ('TRY', 'Turkish Lira (TRY)'),
    ('TTD', 'Trinidad and Tobago Dollar (TTD)'),
    ('TWD', 'New Taiwan Dollar (TWD)'),
    ('TZS', 'Tanzanian Shilling (TZS)'),
    ('UAH', 'Ukrainian Hryvnia (UAH)'),
    ('UGX', 'Ugandan Shilling (UGX)'),
    ('USD', 'United States Dollar (USD)'),
    ('UYU', 'Uruguayan Peso (UYU)'),
    ('UZS', 'Uzbekistan Som (UZS)'),
    ('VES', 'Venezuelan Bolívar Soberano (VES)'),
    ('VND', 'Vietnamese Đồng (VND)'),
    ('VUV', 'Vanuatu Vatu (VUV)'),
    ('WST', 'Samoan Tala (WST)'),
    ('XAF', 'Central African CFA Franc (XAF)'),
    ('XAG', 'Silver (Troy Ounce) (XAG)'),
    ('XAU', 'Gold (Troy Ounce) (XAU)'),
    ('XCD', 'East Caribbean Dollar (XCD)'),
    ('XCG', 'Caribbean Guilder (XCG)'),
    ('XDR', 'Special Drawing Rights (XDR)'),
    ('XOF', 'West African CFA Franc (XOF)'),
    ('XPD', 'Palladium (XPD)'),
    ('XPF', 'CFP Franc (XPF)'),
    ('XPT', 'Platinum (XPT)'),
    ('YER', 'Yemeni Rial (YER)'),
    ('ZAR', 'South African Rand (ZAR)'),
    ('ZMW', 'Zambian Kwacha (ZMW)'),
    ('ZWG', 'Zimbabwe Gold (ZWG)'),
]


class CurrencyService:
    """
    Foreign exchange service powered by Frankfurter API v2 with persistent
    per-date database caching (rate_date).
    """

    API_BASE_URL = "https://api.frankfurter.dev/v2"
    CACHE_DURATION = timedelta(hours=24)
    DEFAULT_HEADERS = {"User-Agent": "SmartContractManager/1.0"}

    def __init__(self, api_url: str | None = None):
        self.api_url = (api_url or self.API_BASE_URL).rstrip('/')

    def get_rate(self, base_currency: str, target_currency: str, as_of: date | None = None) -> float:
        """
        Get exchange rate from base_currency to target_currency.
        If as_of is provided, retrieves the historical rate for that date.
        Uses cached rate if available. For today's rate, refreshes if older than 24 hours.
        """
        base = (base_currency or "EUR").strip().upper()
        target = (target_currency or "EUR").strip().upper()

        if base == target:
            return 1.0

        today = date.today()
        rate_date = as_of if as_of else today
        now = datetime.now(timezone.utc)

        cached = ExchangeRateCache.query.filter_by(
            base_currency=base,
            target_currency=target,
            rate_date=rate_date
        ).first()

        # Immutable historical rate: once cached for a past date, it never expires
        if cached and rate_date < today:
            return cached.rate

        # Today's live rate: check 24-hour cache freshness
        if cached and rate_date >= today and cached.last_updated:
            last_updated = cached.last_updated
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            if now - last_updated < self.CACHE_DURATION:
                return cached.rate

        # Fetch rate from Frankfurter API v2
        try:
            if rate_date >= today:
                # Live / latest rate
                url = f"{self.api_url}/rate/{base}/{target}"
                resp = requests.get(url, headers=self.DEFAULT_HEADERS, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and "rate" in data:
                        rate_val = float(data["rate"])
                    elif isinstance(data, dict) and "rates" in data and target in data["rates"]:
                        rate_val = float(data["rates"][target])
                    else:
                        rate_val = None
                else:
                    logger.warning(f"Frankfurter API v2 error {resp.status_code} for {base}->{target}: {resp.text}")
                    rate_val = None
            else:
                # Historical single date rate
                url = f"{self.api_url}/rates?date={rate_date.isoformat()}&base={base}&quotes={target}"
                resp = requests.get(url, headers=self.DEFAULT_HEADERS, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    # Frankfurter returns a list of rates for time series/single date queries
                    if isinstance(data, list) and len(data) > 0 and "rate" in data[0]:
                        rate_val = float(data[0]["rate"])
                    elif isinstance(data, dict) and "rate" in data:
                        rate_val = float(data["rate"])
                    elif isinstance(data, dict) and "rates" in data and target in data["rates"]:
                        rate_val = float(data["rates"][target])
                    else:
                        rate_val = None
                else:
                    logger.warning(f"Frankfurter API v2 historical error {resp.status_code} for {base}->{target} on {rate_date}: {resp.text}")
                    rate_val = None

            if rate_val is not None:
                if cached:
                    cached.rate = rate_val
                    cached.last_updated = now
                else:
                    cached = ExchangeRateCache(
                        base_currency=base,
                        target_currency=target,
                        rate=rate_val,
                        rate_date=rate_date,
                        last_updated=now,
                    )
                    db.session.add(cached)
                db.session.commit()
                return rate_val

        except Exception as e:
            logger.warning(f"Failed to fetch exchange rate {base}->{target} from API: {e}")

        # Fallback to existing cache if available
        if cached:
            return cached.rate

        # Fallback to most recent known rate in cache
        most_recent = ExchangeRateCache.query.filter_by(
            base_currency=base,
            target_currency=target
        ).order_by(ExchangeRateCache.rate_date.desc()).first()
        if most_recent:
            return most_recent.rate

        return 1.0

    def convert(self, amount: float, from_currency: str, to_currency: str, as_of: date | None = None) -> float:
        """
        Convert amount from from_currency to to_currency, optionally as of a specific date.
        Returns amount rounded to 2 decimal places.
        """
        if not amount:
            return 0.0
        rate = self.get_rate(from_currency, to_currency, as_of=as_of)
        return round(amount * rate, 2)

    def get_active_rates_for_user(self, user: Any, contracts: list[Any]) -> list[dict[str, Any]]:
        """
        Return active exchange rate items for all foreign currencies present in user's contracts.
        """
        target = (getattr(user, 'currency', None) or getattr(user, 'base_currency', None) or "EUR").strip().upper()
        currencies = set()
        for c in contracts:
            c_curr = (getattr(c, 'currency', None) or "EUR").strip().upper()
            if c_curr != target:
                currencies.add(c_curr)

        rates = []
        today = date.today()
        for curr in sorted(currencies):
            rate = self.get_rate(curr, target, as_of=today)
            rates.append({
                "from_currency": curr,
                "to_currency": target,
                "rate": rate,
                "rate_date": today,
            })
        return rates
