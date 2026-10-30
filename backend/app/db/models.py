from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_version: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list[HouseholdMembership]] = relationship(back_populates="user")


class Household(Base):
    __tablename__ = "households"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    country_code: Mapped[str] = mapped_column(String(2), default="GB", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/London", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list[HouseholdMembership]] = relationship(back_populates="household")
    energy_accounts: Mapped[list[EnergyAccount]] = relationship(back_populates="household")


class HouseholdMembership(Base):
    __tablename__ = "household_memberships"
    __table_args__ = (UniqueConstraint("household_id", "user_id", name="uq_household_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(24), default="member", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    household: Mapped[Household] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class EnergyAccount(Base):
    __tablename__ = "energy_accounts"
    __table_args__ = (UniqueConstraint("household_id", "provider", "provider_account_ref", name="uq_household_provider_account"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    provider_account_ref: Mapped[str] = mapped_column(String(160))
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    household: Mapped[Household] = relationship(back_populates="energy_accounts")
    meters: Mapped[list[Meter]] = relationship(back_populates="energy_account")


class Meter(Base):
    __tablename__ = "meters"
    __table_args__ = (UniqueConstraint("energy_account_id", "provider_meter_ref", name="uq_account_meter_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    energy_account_id: Mapped[str] = mapped_column(ForeignKey("energy_accounts.id", ondelete="CASCADE"), index=True)
    provider_meter_ref: Mapped[str] = mapped_column(String(160))
    fuel: Mapped[str] = mapped_column(String(16), default="electricity", nullable=False)
    meter_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    energy_account: Mapped[EnergyAccount] = relationship(back_populates="meters")
    readings: Mapped[list[ElectricityReading]] = relationship(back_populates="meter")
    tariffs: Mapped[list[Tariff]] = relationship(back_populates="meter")


class Tariff(Base):
    __tablename__ = "tariffs"
    __table_args__ = (Index("ix_tariffs_meter_validity", "meter_id", "valid_from", "valid_to"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meter_id: Mapped[str] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), index=True)
    provider_tariff_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tariff_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    standing_charge_p_per_day: Mapped[Decimal | None] = mapped_column(Numeric(12, 5), nullable=True)
    unit_rate_p_per_kwh: Mapped[Decimal | None] = mapped_column(Numeric(12, 5), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="GBP", nullable=False)

    meter: Mapped[Meter] = relationship(back_populates="tariffs")


class ElectricityReading(Base):
    __tablename__ = "electricity_readings"
    __table_args__ = (
        UniqueConstraint("meter_id", "interval_start", "interval_end", name="uq_meter_reading_interval"),
        Index("ix_readings_meter_start", "meter_id", "interval_start"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    meter_id: Mapped[str] = mapped_column(ForeignKey("meters.id", ondelete="CASCADE"), index=True)
    interval_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    interval_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    source_record_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meter: Mapped[Meter] = relationship(back_populates="readings")


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (Index("ix_email_verification_user_expiry", "user_id", "expires_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ix_password_reset_user_expiry", "user_id", "expires_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (Index("ix_refresh_sessions_user_active", "user_id", "revoked_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
