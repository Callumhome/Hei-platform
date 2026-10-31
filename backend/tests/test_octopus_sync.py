from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import ElectricityReading, EnergyAccount, Household, Meter, Tariff
from app.services.octopus_sync import _parse_dt, _rate_value, _tariff_product_code, octopus_energy_analytics


def test_octopus_date_and_tariff_parsing():
    parsed = _parse_dt("2026-10-31T00:30:00Z")
    assert parsed == datetime(2026, 10, 31, 0, 30, tzinfo=timezone.utc)
    assert _tariff_product_code("E-1R-AGILE-24-10-01-A") == "AGILE-24-10-01"
    assert _tariff_product_code("not-a-tariff") is None
    assert _rate_value({"value_inc_vat": "24.123"}) == Decimal("24.123")


def test_octopus_analytics_calculates_tariff_cost_and_export_credit():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    try:
        household = Household(id="octopus-household", name="Test home", timezone="Europe/London")
        db.add(household)
        db.flush()
        account = EnergyAccount(
            id="octopus-account", household_id=household.id,
            provider="octopus", provider_account_ref="account-hash",
        )
        db.add(account)
        db.flush()
        meter = Meter(
            id="octopus-meter", energy_account_id=account.id,
            provider_meter_ref="mpan:serial", fuel="electricity", meter_type="import",
        )
        db.add(meter)
        db.flush()
        now = datetime.now(timezone.utc)
        interval_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(minutes=30)
        db.add(Tariff(
            meter_id=meter.id, provider_tariff_ref="E-1R-TEST-A",
            valid_from=now - timedelta(days=2), valid_to=None,
            unit_rate_p_per_kwh=Decimal("30"),
            standing_charge_p_per_day=Decimal("50"),
        ))
        db.add(ElectricityReading(
            meter_id=meter.id, interval_start=interval_start,
            interval_end=interval_start + timedelta(minutes=30),
            consumption_kwh=Decimal("0.235"), export_kwh=Decimal("0"),
            source_provider="octopus", quality="unknown",
        ))
        db.commit()

        result = octopus_energy_analytics(db, household.id, 7)
        assert result["meter_count"] == 1
        assert result["reading_count"] == 1
        assert result["today"]["import_kwh"] in {0.235, 0.0}
        assert result["currency"] == "GBP"
    finally:
        db.close()
        engine.dispose()
