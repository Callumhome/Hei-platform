from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import configure_mappers

from app.db.base import Base
from app.db import models  # noqa: F401 - registers all model tables


def test_all_household_energy_tables_register():
    expected = {
        "users",
        "households",
        "household_memberships",
        "energy_accounts",
        "meters",
        "tariffs",
        "electricity_readings",
        "properties",
        "meter_points",
        "provider_connections",
        "consent_records",
        "energy_data_readings",
        "sync_jobs",
    }
    assert expected.issubset(set(Base.metadata.tables))


def test_models_create_in_sqlite():
    engine = create_engine("sqlite:///:memory:")
    configure_mappers()
    Base.metadata.create_all(engine)
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables)
    engine.dispose()


def test_cloud_energy_models_keep_sensitive_identifiers_encrypted():
    assert "address_encrypted" in Base.metadata.tables["properties"].columns
    assert "postcode_fingerprint" in Base.metadata.tables["properties"].columns
    assert "identifier_encrypted" in Base.metadata.tables["meter_points"].columns
    assert "identifier_fingerprint" in Base.metadata.tables["meter_points"].columns
