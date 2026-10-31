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
    export_kwh: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    source_provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    quality: Mapped[str] = mapped_column(String(24), default="unknown", nullable=False)
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


class HomeAssistantConnection(Base):
    __tablename__ = "home_assistant_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(300), nullable=False)
    token_encrypted: Mapped[str] = mapped_column(String(8192), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Property(Base):
    __tablename__ = "properties"
    __table_args__ = (UniqueConstraint("household_id", "property_ref", name="uq_property_household_ref"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    property_ref: Mapped[str] = mapped_column(String(80), nullable=False)
    address_line_1: Mapped[str] = mapped_column(String(160), nullable=False)
    address_line_2: Mapped[str | None] = mapped_column(String(160), nullable=True)
    town: Mapped[str] = mapped_column(String(120), nullable=False)
    county: Mapped[str | None] = mapped_column(String(120), nullable=True)
    postcode: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    country_code: Mapped[str] = mapped_column(String(2), default="GB", nullable=False)
    address_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address_source_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupplyPoint(Base):
    __tablename__ = "supply_points"
    __table_args__ = (UniqueConstraint("property_id", "fuel", "identifier_hash", name="uq_supply_point_property_fuel_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    property_id: Mapped[str] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), index=True)
    fuel: Mapped[str] = mapped_column(String(16), nullable=False)
    identifier_encrypted: Mapped[str] = mapped_column(String(2048), nullable=False)
    identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    identifier_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    supplier_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="unverified", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConsentGrant(Base):
    __tablename__ = "consent_grants"
    __table_args__ = (Index("ix_consent_household_status", "household_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    property_id: Mapped[str | None] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    purpose: Mapped[str] = mapped_column(String(200), nullable=False)
    scopes_json: Mapped[str] = mapped_column(String(2000), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SyncJob(Base):
    __tablename__ = "sync_jobs"
    __table_args__ = (
        Index("ix_sync_jobs_household_created", "household_id", "created_at"),
        Index("ix_sync_jobs_status_next", "status", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    job_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=5, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OctopusConnection(Base):
    __tablename__ = "octopus_connections"
    __table_args__ = (UniqueConstraint("household_id", name="uq_octopus_connection_household"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(ForeignKey("households.id", ondelete="CASCADE"), index=True)
    account_number_encrypted: Mapped[str] = mapped_column(String(2048), nullable=False)
    account_number_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    account_number_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    api_key_encrypted: Mapped[str] = mapped_column(String(2048), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
