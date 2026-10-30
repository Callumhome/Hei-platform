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
    }
    assert expected.issubset(set(Base.metadata.tables))


def test_models_create_in_sqlite():
    engine = create_engine("sqlite:///:memory:")
    configure_mappers()
    Base.metadata.create_all(engine)
    assert set(inspect(engine).get_table_names()) == set(Base.metadata.tables)
    engine.dispose()
