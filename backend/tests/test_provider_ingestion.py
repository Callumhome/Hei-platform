from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import EnergyAccount, Household, Meter
from app.providers.adapter_registry import clear_registry, get_adapter, register_adapter
from app.providers.contracts import NormalizedReading, ReadingPage
from app.providers.fake import FakeProvider
from app.services.ingestion import (
    create_sync_job, ingest_reading_page, mark_sync_failed,
    mark_sync_started, mark_sync_succeeded,
)


def _database():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    household = Household(id="household-1", name="Test home")
    session.add(household)
    session.flush()
    account = EnergyAccount(id="account-1", household_id=household.id, provider="fake", provider_account_ref="acct-1")
    session.add(account)
    session.flush()
    meter = Meter(id="meter-1", energy_account_id=account.id, provider_meter_ref="meter-ref", fuel="electricity")
    session.add(meter)
    session.commit()
    return engine, session, household, meter


def test_normalized_reading_requires_timezone_and_valid_interval():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    NormalizedReading(start, start + timedelta(minutes=30), Decimal("0.25"), Decimal("0.10")).validate()
    with pytest.raises(ValueError, match="timezone"):
        NormalizedReading(datetime(2026, 1, 1), start + timedelta(minutes=30), Decimal("1")).validate()
    with pytest.raises(ValueError, match="non-negative"):
        NormalizedReading(start, start + timedelta(minutes=30), Decimal("-1")).validate()


def test_fake_adapter_paginates_without_network_calls():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    reading = NormalizedReading(start, start + timedelta(minutes=30), Decimal("0.3"))
    adapter = FakeProvider({None: ReadingPage((reading,), "page-2"), "page-2": ReadingPage(())})
    import asyncio
    first = asyncio.run(adapter.fetch_readings("meter-1"))
    second = asyncio.run(adapter.fetch_readings("meter-1", cursor=first.next_cursor))
    assert len(first.readings) == 1
    assert second.readings == ()
    assert adapter.calls == [("meter-1", None, 100), ("meter-1", "page-2", 100)]


def test_adapter_registry_rejects_duplicates():
    clear_registry()
    adapter = FakeProvider()
    register_adapter(adapter)
    assert get_adapter("fake") is adapter
    with pytest.raises(ValueError, match="already registered"):
        register_adapter(adapter)
    clear_registry()


def test_ingestion_is_idempotent_and_keeps_import_export_separate():
    engine, db, household, meter = _database()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    reading = NormalizedReading(start, start + timedelta(minutes=30), Decimal("0.4"), Decimal("0.1"), "actual", "row-1")
    assert ingest_reading_page(db, meter_id=meter.id, provider="fake", readings=(reading,)) == (1, 0)
    db.commit()
    assert ingest_reading_page(db, meter_id=meter.id, provider="fake", readings=(reading,)) == (0, 1)
    stored = db.query(__import__("app.db.models", fromlist=["ElectricityReading"]).ElectricityReading).one()
    assert stored.consumption_kwh == Decimal("0.400000")
    assert stored.export_kwh == Decimal("0.100000")
    assert stored.source_provider == "fake"
    assert stored.quality == "actual"
    db.close()
    engine.dispose()


def test_sync_job_retry_backoff_and_success_lifecycle():
    engine, db, household, _ = _database()
    job = create_sync_job(db, household_id=household.id, provider="FAKE", job_type="readings", max_attempts=2)
    assert job.provider == "fake"
    mark_sync_started(db, job)
    mark_sync_failed(db, job, error_code="TEMPORARY", error_message="Provider temporarily unavailable")
    assert job.status == "retry"
    assert job.attempts == 1
    assert job.next_attempt_at is not None
    mark_sync_started(db, job)
    mark_sync_succeeded(db, job, cursor="next-page")
    assert job.status == "succeeded"
    assert job.cursor == "next-page"
    db.close()
    engine.dispose()
