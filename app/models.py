import enum
from datetime import datetime, timezone
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
