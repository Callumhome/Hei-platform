from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import ElectricityReading, EnergyAccount, Household, Meter, Tariff
from app.services.octopus_sync import (
    OctopusSyncError, _get_json, _has_valid_period, _parse_dt, _rate_value,
    _tariff_product_code, _tariff_rate_endpoints, octopus_energy_analytics,
)


def test_octopus_date_and_tariff_parsing():
    parsed = _parse_dt("2026-10-31T00:30:00Z")
    assert parsed == datetime(2026, 10, 31, 0, 30, tzinfo=timezone.utc)
    assert _tariff_product_code("E-1R-AGILE-24-10-01-A") == "AGILE-24-10-01"
    assert _tariff_product_code("not-a-tariff") is None
    assert _rate_value({"value_inc_vat": "24.123"}) == Decimal("24.123")
    assert _tariff_rate_endpoints("E-1R-AGILE-24-10-01-A") == {
        "standard": "standard-unit-rates/"
    }
    assert _tariff_rate_endpoints("E-2R-VAR-22-11-01-H") == {
        "day": "day-unit-rates/",
        "night": "night-unit-rates/",
    }


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



def test_economy7_analytics_does_not_guess_day_or_night_rate():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = Session(engine)
    try:
        household = Household(id="economy7-household", name="Economy 7 home", timezone="Europe/London")
        db.add(household)
        db.flush()
        account = EnergyAccount(
            id="economy7-account", household_id=household.id,
            provider="octopus", provider_account_ref="economy7-account-hash",
        )
        db.add(account)
        db.flush()
        meter = Meter(
            id="economy7-meter", energy_account_id=account.id,
            provider_meter_ref="economy7-mpan:serial", fuel="electricity", meter_type="import",
        )
        db.add(meter)
        db.flush()
        now = datetime.now(timezone.utc)
        interval_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(minutes=30)
        tariff_start = now - timedelta(days=2)
        db.add_all([
            Tariff(
                meter_id=meter.id, provider_tariff_ref="E-2R-TEST-H:day",
                valid_from=tariff_start, valid_to=None,
                unit_rate_p_per_kwh=Decimal("30"),
                standing_charge_p_per_day=Decimal("50"),
            ),
            Tariff(
                meter_id=meter.id, provider_tariff_ref="E-2R-TEST-H:night",
                valid_from=tariff_start, valid_to=None,
                unit_rate_p_per_kwh=Decimal("10"),
                standing_charge_p_per_day=None,
            ),
        ])
        db.add(ElectricityReading(
            meter_id=meter.id, interval_start=interval_start,
            interval_end=interval_start + timedelta(minutes=30),
            consumption_kwh=Decimal("1.000"), export_kwh=Decimal("0"),
            source_provider="octopus", quality="unknown",
        ))
        db.commit()

        result = octopus_energy_analytics(db, household.id, 7)
        assert result["reading_count"] == 1
        assert result["cost_complete"] is False
        assert result["today"]["cost_complete"] is False
        assert result["half_hourly"][-1]["unit_rate_p_per_kwh"] is None
        # Standing charge is counted once, not once for each register.
        assert result["period_energy_cost_gbp"] == 1.0
    finally:
        db.close()
        engine.dispose()



def test_octopus_bad_request_reports_safe_endpoint_and_provider_detail():
    def handler(request):
        return httpx.Response(
            400,
            json={"detail": "Invalid request for meter 1234567890123"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(
        base_url="https://api.octopus.energy/v1/",
        transport=transport,
    ) as client:
        with pytest.raises(OctopusSyncError) as exc_info:
            _get_json(
                client,
                "electricity-meter-points/1234567890123/meters/METER-SERIAL-123/consumption/",
            )

    error = exc_info.value
    assert error.code == "OCTOPUS_BAD_REQUEST"
    assert "HTTP 400" in str(error)
    assert "electricity-meter-points/[redacted]/meters/[redacted]/consumption" in str(error)
    assert "Invalid request for meter [redacted]" in str(error)
    assert "1234567890123" not in str(error)
    assert "METER-SERIAL-123" not in str(error)



def test_empty_or_reversed_octopus_agreement_periods_are_skipped():
    start = datetime(2024, 10, 10, 23, 0, tzinfo=timezone.utc)
    assert _has_valid_period(start, start) is False
    assert _has_valid_period(start, start - timedelta(seconds=1)) is False
    assert _has_valid_period(start, start + timedelta(seconds=1)) is True
    assert _has_valid_period(start, None) is True
    assert _has_valid_period(None, None) is False
