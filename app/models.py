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
    scheduled = "scheduled"
    active = "active"
    pending_cancellation = "pending_cancellation"
    cancellation_confirmed = "cancellation_confirmed"
    paused = "paused"
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
    full_name = Column(String(120), nullable=True)
    address = Column(Text, nullable=True)
    timezone = Column(String(64), default="Europe/Berlin")
    currency = Column(String(8), default="EUR")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    providers = relationship("Provider", back_populates="owner", cascade="all, delete-orphan")
    contracts = relationship("Contract", back_populates="owner", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="owner", cascade="all, delete-orphan")
    notes = relationship("Note", back_populates="owner", cascade="all, delete-orphan")


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
    notes_list = relationship("Note", back_populates="provider", cascade="all, delete-orphan", order_by="Note.created_at.desc()")


class Tag(db.Model):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(64), nullable=False)
    color = Column(String(16), default="#0d6efd", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="tags")
    contracts = relationship("Contract", secondary=contract_tags, back_populates="tags")


class Note(db.Model):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    contract_id = Column(Integer, ForeignKey("contracts.id"), nullable=True, index=True)
    provider_id = Column(Integer, ForeignKey("providers.id"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="notes")
    contract = relationship("Contract", back_populates="notes_list")
    provider = relationship("Provider", back_populates="notes_list")


def add_months(sourcedate: date, months: int) -> date:
    """Add months to a date, pinning to the last day of the month if overflow occurs."""
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def subtract_notice(target_date: date, notice_amount: int, notice_unit: str) -> date:
    """Subtract a notice duration from a target date."""
    unit = (notice_unit or "days").lower()
    if unit == "months":
        return add_months(target_date, -notice_amount)
    elif unit == "weeks":
        return target_date - timedelta(weeks=notice_amount)
    else:
        return target_date - timedelta(days=notice_amount)


def snap_to_target_period(target_date: date, period_type: str | None) -> date:
    """Snaps a date to the relevant termination anchor according to contract terms."""
    if not period_type or period_type == "exact":
        return target_date
    if period_type == "end_of_month":
        last_day = calendar.monthrange(target_date.year, target_date.month)[1]
        return date(target_date.year, target_date.month, last_day)
    elif period_type == "end_of_quarter":
        q_month = ((target_date.month - 1) // 3 + 1) * 3
        last_day = calendar.monthrange(target_date.year, q_month)[1]
        return date(target_date.year, q_month, last_day)
    elif period_type == "end_of_year":
        return date(target_date.year, 12, 31)
    return target_date


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
    title = Column(String(120), nullable=False, default="")
    category = Column(String(80), nullable=False, default="Sonstiges")
    status = Column(Enum(ContractStatus), default=ContractStatus.active, nullable=False)
    contract_number = Column(String(120), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    billing_anchor_date = Column(Date, nullable=True)
    cancellation_notice_amount = Column(Integer, default=0)
    cancellation_notice_unit = Column(String(16), default="days")
    cancellation_target_period = Column(String(32), default="exact", nullable=False)
    initial_term_months = Column(Integer, default=0, nullable=True)
    initial_term_end_date = Column(Date, nullable=True)
    renewal_period_months = Column(Integer, default=1, nullable=True)
    renewal_type = Column(String(32), default="monthly_rolling", nullable=True)
    cancellation_sent_date = Column(Date, nullable=True)
    confirmed_end_date = Column(Date, nullable=True)
    amount = Column(Float, default=0.0)
    currency = Column(String(8), default="EUR")
    frequency = Column(Enum(Frequency), default=Frequency.monthly, nullable=False)
    payment_method = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    owner = relationship("User", back_populates="contracts")
    provider = relationship("Provider", back_populates="contracts")
    tags = relationship("Tag", secondary=contract_tags, back_populates="contracts")
    documents = relationship("Document", back_populates="contract", cascade="all, delete-orphan")
    notes_list = relationship("Note", back_populates="contract", cascade="all, delete-orphan", order_by="Note.created_at.desc()")
    price_history = relationship(
        "PriceEntry",
        back_populates="contract",
        cascade="all, delete-orphan",
        order_by="PriceEntry.valid_from.desc()",
    )

    def get_price_on_date(self, on_date: date) -> tuple[float, str]:
        """Returns the effective (amount, currency) on a given date."""
        if self.price_history:
            for p in self.price_history:
                if p.valid_from <= on_date:
                    if p.valid_to is None or p.valid_to >= on_date:
                        return float(p.amount), p.currency
        return float(self.amount or 0.0), self.currency or "EUR"

    @property
    def current_price_entry(self):
        """Returns the PriceEntry effective as of today, if any."""
        today = date.today()
        if not self.price_history:
            return None
        for p in self.price_history:
            if p.valid_from <= today:
                if p.valid_to is None or p.valid_to >= today:
                    return p
        return None

    @property
    def current_amount(self) -> float:
        """Effective amount today, falling back to contract.amount."""
        curr_p = self.current_price_entry
        if curr_p:
            return float(curr_p.amount)
        return float(self.amount or 0.0)

    @property
    def current_currency(self) -> str:
        """Effective currency today, falling back to contract.currency."""
        curr_p = self.current_price_entry
        if curr_p:
            return curr_p.currency
        return self.currency or "EUR"

    @property
    def upcoming_price_entries(self):
        """Returns future price entries representing an actual price change."""
        today = date.today()
        if not self.price_history:
            return []
        ref_date = self.start_date if (self.start_date and self.start_date > today) else today
        curr_amt = self.current_amount
        curr_curr = self.current_currency

        futures = [
            p for p in self.price_history
            if p.valid_from > ref_date and (round(float(p.amount), 2) != round(curr_amt, 2) or p.currency != curr_curr)
        ]
        return sorted(futures, key=lambda p: p.valid_from)

    @property
    def next_price_change(self):
        """Returns the earliest upcoming price entry if one is scheduled."""
        upcoming = self.upcoming_price_entries
        return upcoming[0] if upcoming else None

    @property
    def price_delta_to_next(self) -> dict | None:
        """Calculates delta between current price and next scheduled price change."""
        next_p = self.next_price_change
        if not next_p:
            return None
        curr_amt = self.current_amount
        diff = round(float(next_p.amount) - curr_amt, 2)
        pct = round((diff / curr_amt) * 100, 1) if curr_amt > 0 else 0.0
        return {
            "diff_amount": diff,
            "abs_diff_amount": abs(diff),
            "diff_percent": pct,
            "abs_diff_percent": abs(pct),
            "is_reduction": diff < 0,
            "is_increase": diff > 0,
            "currency": next_p.currency,
        }

    @property
    def amount_on_next_billing(self) -> float | None:
        """Calculates the amount that will actually be charged on next_billing_date."""
        nbd = self.next_billing_date
        if not nbd:
            return None
        amt, _ = self.get_price_on_date(nbd)
        return amt

    @property
    def next_billing_date(self) -> date | None:
        """Returns the next upcoming billing date for the contract, or None if contract ended or has no anchor."""
        return self.get_next_billing_date()

    def get_next_billing_date(self, as_of: date | None = None) -> date | None:
        """Calculate the next billing date >= as_of based on billing_anchor_date and frequency."""
        if not self.billing_anchor_date:
            return None
        if self.is_archived or self.status in (ContractStatus.paused, ContractStatus.canceled, ContractStatus.archived):
            return None
        if as_of is None:
            as_of = date.today()
        if self.start_date and self.start_date > as_of:
            as_of = self.start_date

        effective_end = self.confirmed_end_date or self.end_date
        if effective_end and effective_end < as_of:
            return None

        next_date = calculate_next_billing_date(self.billing_anchor_date, self.frequency, as_of)

        if effective_end and next_date > effective_end:
            return None

        return next_date

    def sync_contract_status(self, as_of: date | None = None) -> bool:
        """Auto-transitions contract statuses based on dates:
        1. scheduled -> active if start_date is reached (today >= start_date).
        2. cancellation_confirmed -> canceled if effective end date is in the past.
        """
        today = as_of if as_of is not None else date.today()
        if self.status == ContractStatus.scheduled:
            if not self.start_date or today >= self.start_date:
                self.status = ContractStatus.active
                return True

        if self.status == ContractStatus.cancellation_confirmed:
            effective_end = self.confirmed_end_date or self.end_date
            if effective_end and today > effective_end:
                self.status = ContractStatus.canceled
                return True
        return False

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
        effective_end = self.confirmed_end_date or self.end_date
        if not effective_end:
            return None
        return (effective_end - date.today()).days

    def get_earliest_cancellation_date(self, as_of: date | None = None) -> date | None:
        """
        Calculates the earliest legally possible contract termination date based on:
        - confirmed_end_date (if cancellation confirmed or explicitly set)
        - end_date (if set and deadline not passed, or renewal_type == 'none')
        - start_date, initial_term_months, renewal_type, renewal_period_months, and notice period
        """
        if self.status == ContractStatus.cancellation_confirmed and self.confirmed_end_date:
            return self.confirmed_end_date

        if self.confirmed_end_date:
            return self.confirmed_end_date

        ref = as_of or date.today()

        # Pure open-ended contract without dates or commitment
        if not self.end_date and not self.start_date and not self.billing_anchor_date and not (self.initial_term_months and self.initial_term_months > 0):
            return None

        notice_amt = self.cancellation_notice_amount or 0
        notice_unit = self.cancellation_notice_unit or "days"

        # Explicit end_date takes priority if no rollover or if deadline not yet passed
        if self.end_date:
            dl = subtract_notice(self.end_date, notice_amt, notice_unit) if notice_amt > 0 else self.end_date
            if self.renewal_type == "none" or ref <= dl:
                return self.end_date

        start = self.start_date or self.billing_anchor_date or ref
        target_period = getattr(self, "cancellation_target_period", "exact") or "exact"

        # Calculate initial term end
        if self.initial_term_end_date:
            initial_end = snap_to_target_period(self.initial_term_end_date, target_period)
        elif self.initial_term_months and self.initial_term_months > 0:
            initial_end = snap_to_target_period(add_months(start, self.initial_term_months), target_period)
        else:
            initial_end = start

        # Check deadline for initial term
        initial_deadline = subtract_notice(initial_end, notice_amt, notice_unit) if notice_amt > 0 else initial_end

        if initial_end > start and ref <= initial_deadline:
            return initial_end

        # If past initial term or initial deadline passed:
        r_type = self.renewal_type or "monthly_rolling"
        if r_type == "none":
            return self.end_date or initial_end

        step_months = self.renewal_period_months or (1 if r_type == "monthly_rolling" else 12)
        if step_months < 1:
            step_months = 1

        cand_end = self.end_date or initial_end
        cycles = 0
        while cycles < 120:
            cycles += 1
            cand_end = snap_to_target_period(cand_end, target_period)
            if cand_end > ref or (cycles > 1 and cand_end >= ref):
                deadline = subtract_notice(cand_end, notice_amt, notice_unit) if notice_amt > 0 else cand_end
                if deadline >= ref:
                    return cand_end
            cand_end = add_months(cand_end, step_months)

        return snap_to_target_period(cand_end, target_period)

    @property
    def earliest_cancellation_date(self) -> date | None:
        """Earliest possible contract termination date from today."""
        return self.get_earliest_cancellation_date()

    def get_cancellation_deadline(self, as_of: date | None = None) -> date | None:
        """Calculates the deadline by which notice must be received."""
        if self.is_archived or (self.status and self.status in (ContractStatus.canceled, ContractStatus.archived, ContractStatus.cancellation_confirmed)):
            return None
        if not self.cancellation_notice_amount or self.cancellation_notice_amount <= 0:
            return None

        # If an explicit end_date is set, its notice deadline takes precedence
        if self.end_date:
            return subtract_notice(self.end_date, self.cancellation_notice_amount, self.cancellation_notice_unit)

        earliest_end = self.get_earliest_cancellation_date(as_of=as_of)
        if not earliest_end:
            return None

        return subtract_notice(earliest_end, self.cancellation_notice_amount, self.cancellation_notice_unit)

    @property
    def cancellation_deadline(self) -> date | None:
        """Calculates the next cancellation deadline from today."""
        return self.get_cancellation_deadline()

    @property
    def days_until_cancellation_deadline(self) -> int | None:
        """Number of days until the cancellation deadline from today."""
        dl = self.cancellation_deadline
        if not dl:
            return None
        return (dl - date.today()).days

    @property
    def is_monthly_flexible(self) -> bool:
        """Returns True if the contract rolls monthly without an active longer lock-in period."""
        if self.renewal_type == "none" or self.end_date:
            return False
        r_type = self.renewal_type or "monthly_rolling"
        period = self.renewal_period_months or 1
        if r_type != "monthly_rolling" and period > 1:
            return False
        today = date.today()
        # Check if currently locked in by initial term
        if self.initial_term_end_date:
            if today < self.initial_term_end_date:
                return False
        elif self.initial_term_months and self.initial_term_months > 0:
            start = self.start_date or self.billing_anchor_date
            if start:
                target_period = getattr(self, "cancellation_target_period", "exact") or "exact"
                initial_end = snap_to_target_period(add_months(start, self.initial_term_months), target_period)
                if today < initial_end:
                    return False
        return True

    @property
    def cancellation_status(self) -> str:
        """
        Status of the cancellation deadline:
        - 'none': No deadline defined (no notice specified, or contract not active/pending)
        - 'flexible': Monthly flexible rolling contract (no urgent lock-in deadline)
        - 'missed': Deadline has passed
        - 'due_today': Deadline is today (0 days left)
        - 'urgent': Deadline is within the next 30 days
        - 'safe': Deadline is more than 30 days in the future
        - 'ended': Contract has ended
        """
        if self.status and self.status not in (ContractStatus.active, ContractStatus.pending_cancellation):
            return 'none'
        if not self.cancellation_notice_amount or not self.cancellation_deadline:
            return 'none'
        effective_end = self.confirmed_end_date or self.end_date or self.earliest_cancellation_date
        today = date.today()
        if effective_end and effective_end < today:
            return 'ended'
        if self.is_monthly_flexible:
            return 'flexible'
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
        effective_end = self.confirmed_end_date or self.end_date or self.earliest_cancellation_date
        if not effective_end:
            return "unlimited"
        ref_date = as_of or date.today()
        if effective_end < ref_date:
            return "ended"
        diff_days = (effective_end - ref_date).days
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

    def get_status(self, as_of: date | None = None) -> str:
        """Returns 'future', 'current', or 'past' relative to as_of (default date.today())."""
        ref = as_of or date.today()
        if self.valid_from > ref:
            return "future"
        if self.valid_to is not None and self.valid_to < ref:
            return "past"
        return "current"

    @property
    def status(self) -> str:
        """Dynamic status: 'future', 'current', or 'past' relative to today."""
        return self.get_status()

    @property
    def is_future(self) -> bool:
        return self.valid_from > date.today()

    @property
    def is_currently_active(self) -> bool:
        today = date.today()
        return self.valid_from <= today and (self.valid_to is None or self.valid_to >= today)

    @property
    def is_past(self) -> bool:
        return self.valid_to is not None and self.valid_to < date.today()



class ExchangeRateCache(db.Model):
    __tablename__ = "exchange_rate_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    base_currency = Column(String(8), nullable=False)
    target_currency = Column(String(8), nullable=False)
    rate = Column(Float, nullable=False)
    last_updated = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
