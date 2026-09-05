import calendar
import enum
from datetime import date, datetime, timedelta, timezone
from flask_login import UserMixin
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Table,
    Text,
    Enum,
    Boolean,
)
from sqlalchemy.orm import relationship

from app import db


class ContractStatus(str, enum.Enum):
    active = "active"
    canceled = "canceled"
    archived = "archived"


class Frequency(str, enum.Enum):
    weekly = "weekly"
    biweekly = "biweekly"
    monthly = "monthly"
    quarterly = "quarterly"
    yearly = "yearly"


contract_tags = Table(
    "contract_tags",
    db.metadata,
    Column("contract_id", ForeignKey("contracts.id"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    hashed_password = Column(String(256), nullable=False)
    timezone = Column(String(64), default="Europe/Berlin")
    currency = Column(String(8), default="EUR")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    providers = relationship("Provider", back_populates="owner", cascade="all, delete-orphan")
    contracts = relationship("Contract", back_populates="owner", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="owner", cascade="all, delete-orphan")


class Provider(db.Model):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(120), nullable=False)
    customer_number = Column(String(80), nullable=True)
    address = Column(Text, nullable=True)
    email = Column(String(120), nullable=True)
    phone = Column(String(50), nullable=True)
    website = Column(String(255), nullable=True)
    customer_portal = Column(String(255), nullable=True)
    cancel_url = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="providers")
    contracts = relationship("Contract", back_populates="provider")


class Tag(db.Model):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(64), nullable=False)
    color = Column(String(16), default="#0d6efd", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="tags")
    contracts = relationship("Contract", secondary=contract_tags, back_populates="tags")


def add_months(sourcedate: date, months: int) -> date:
    """Add months to a date, pinning to the last day of the month if overflow occurs."""
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate_next_billing_date(anchor_date: date, frequency: Frequency, as_of: date) -> date:
    """Calculate the next payment date on or after `as_of` according to payment frequency."""
    if anchor_date >= as_of:
        return anchor_date

    if frequency == Frequency.weekly:
        diff_days = (as_of - anchor_date).days
        steps = (diff_days + 6) // 7
        return anchor_date + timedelta(weeks=steps)
    elif frequency == Frequency.biweekly:
        diff_days = (as_of - anchor_date).days
        steps = (diff_days + 13) // 14
        return anchor_date + timedelta(weeks=2 * steps)
    elif frequency == Frequency.monthly:
        m_step = 1
    elif frequency == Frequency.quarterly:
        m_step = 3
    elif frequency == Frequency.yearly:
        m_step = 12
    else:
        m_step = 1

    month_diff = (as_of.year - anchor_date.year) * 12 + (as_of.month - anchor_date.month)
    steps = max(0, month_diff // m_step)
    candidate = add_months(anchor_date, steps * m_step)
    while candidate < as_of:
        steps += 1
        candidate = add_months(anchor_date, steps * m_step)
    return candidate


class Contract(db.Model):
    __tablename__ = "contracts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True)
    category = Column(String(80), nullable=False, default="Sonstiges")
    status = Column(Enum(ContractStatus), default=ContractStatus.active, nullable=False)
    contract_number = Column(String(120), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    billing_anchor_date = Column(Date, nullable=True)
    cancellation_notice_amount = Column(Integer, default=0)
    cancellation_notice_unit = Column(String(16), default="days")
    amount = Column(Float, default=0.0)
    currency = Column(String(8), default="EUR")
    frequency = Column(Enum(Frequency), default=Frequency.monthly, nullable=False)
    payment_term = Column(String(64), nullable=True)
    payment_method = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="contracts")
    provider = relationship("Provider", back_populates="contracts")
    tags = relationship("Tag", secondary=contract_tags, back_populates="contracts")
    documents = relationship("Document", back_populates="contract", cascade="all, delete-orphan")
    price_history = relationship(
        "PriceEntry",
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="PriceEntry.valid_from.desc()",
    )

    @property
    def next_billing_date(self) -> date | None:
        """Returns the next upcoming billing date for the contract, or None if contract ended or has no anchor."""
        return self.get_next_billing_date()

    def get_next_billing_date(self, as_of: date | None = None) -> date | None:
        """Calculate the next billing date >= as_of based on billing_anchor_date and frequency."""
        if not self.billing_anchor_date:
            return None
        if as_of is None:
            as_of = date.today()

        if self.end_date and self.end_date < as_of:
            return None

        next_date = calculate_next_billing_date(self.billing_anchor_date, self.frequency, as_of)

        if self.end_date and next_date > self.end_date:
            return None

        return next_date

    @property
    def days_until_next_billing(self) -> int | None:
        """Number of calendar days until next billing date from today."""
        nbd = self.next_billing_date
        if not nbd:
            return None
        return (nbd - date.today()).days

    @property
    def days_until_end(self) -> int | None:
        """Number of calendar days until contract end date from today, or None if open-ended."""
        if not self.end_date:
            return None
        return (self.end_date - date.today()).days

    @property
    def cancellation_deadline(self) -> date | None:
        """Calculates the latest cancellation date: end_date minus notice period for active contracts."""
        if self.status and self.status != ContractStatus.active:
            return None
        if not self.end_date or not self.cancellation_notice_amount or self.cancellation_notice_amount <= 0:
            return None
        unit = (self.cancellation_notice_unit or "days").lower()
        if unit == "months":
            return add_months(self.end_date, -self.cancellation_notice_amount)
        elif unit == "weeks":
            return self.end_date - timedelta(weeks=self.cancellation_notice_amount)
        else:
            return self.end_date - timedelta(days=self.cancellation_notice_amount)

    @property
    def days_until_cancellation_deadline(self) -> int | None:
        """Number of days until the cancellation deadline from today."""
        dl = self.cancellation_deadline
        if not dl:
            return None
        return (dl - date.today()).days

    @property
    def cancellation_status(self) -> str:
        """
        Status of the cancellation deadline:
        - 'none': No deadline defined (open-ended, no notice specified, or contract not active)
        - 'missed': Deadline has passed, but contract end_date is still in future
        - 'due_today': Deadline is today (0 days left)
        - 'urgent': Deadline is within the next 30 days
        - 'safe': Deadline is more than 30 days in the future
        - 'ended': Contract end_date is in the past
        """
        if self.status and self.status != ContractStatus.active:
            return 'none'
        if not self.end_date or not self.cancellation_deadline:
            return 'none'
        today = date.today()
        if self.end_date < today:
            return 'ended'
        days = self.days_until_cancellation_deadline
        if days is None:
            return 'none'
        if days < 0:
            return 'missed'
        elif days == 0:
            return 'due_today'
        elif days <= 30:
            return 'urgent'
        else:
            return 'safe'

    def get_remaining_term_human(self, as_of: date | None = None) -> str:
        """Returns a human-readable remaining term representation token."""
        if not self.end_date:
            return "unlimited"
        ref_date = as_of or date.today()
        if self.end_date < ref_date:
            return "ended"
        diff_days = (self.end_date - ref_date).days
        if diff_days == 0:
            return "ends_today"
        if diff_days < 30:
            return f"{diff_days}d"
        years = diff_days // 365
        rem_days = diff_days % 365
        months = rem_days // 30
        if years > 0:
            if months > 0:
                return f"{years}y {months}m"
            return f"{years}y"
        return f"{months}m" if months > 0 else f"{diff_days}d"

    @property
    def remaining_term_human(self) -> str:
        return self.get_remaining_term_human()


class Document(db.Model):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    extracted_text = Column(Text, nullable=True)

    contract = relationship("Contract", back_populates="documents")


class PriceEntry(db.Model):
    __tablename__ = "price_entries"

    id = Column(Integer, primary_key=True, index=True)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=False)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    is_current = Column(Boolean, default=True, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False, default="EUR")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    contract = relationship("Contract", back_populates="price_history")

    @property
    def effective_date(self):
        return self.valid_from

    @effective_date.setter
    def effective_date(self, value):
        self.valid_from = value


class ExchangeRateCache(db.Model):
    __tablename__ = "exchange_rate_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    base_currency = Column(String(8), nullable=False)
    target_currency = Column(String(8), nullable=False)
    rate = Column(Float, nullable=False)
    last_updated = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
