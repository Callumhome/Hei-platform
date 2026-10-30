from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import get_db
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def register(email: str) -> str:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "a-very-long-test-password"})
    assert response.status_code == 201
    return response.json()["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def household(token: str, name: str) -> str:
    response = client.post("/api/v1/households", headers=headers(token), json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def test_energy_accounts_are_scoped_to_household_and_role():
    owner = register("owner@example.com")
    member = register("member@example.com")
    outsider = register("outsider@example.com")
    home_id = household(owner, "Owner home")
    other_home_id = household(outsider, "Other home")

    created = client.post(
        f"/api/v1/households/{home_id}/energy-accounts",
        headers=headers(owner),
        json={"provider": "octopus", "provider_account_ref": "account-123", "label": "Main supply"},
    )
    assert created.status_code == 201
    account_id = created.json()["id"]

    assert client.get(f"/api/v1/households/{home_id}/energy-accounts", headers=headers(member)).status_code == 200
    assert client.get(f"/api/v1/households/{home_id}/energy-accounts", headers=headers(outsider)).status_code == 404
    assert client.get(f"/api/v1/households/{other_home_id}/energy-accounts", headers=headers(outsider)).json() == []
    assert client.post(
        f"/api/v1/households/{home_id}/energy-accounts",
        headers=headers(member),
        json={"provider": "octopus", "provider_account_ref": "member-write"},
    ).status_code == 403

    meter = client.post(
        f"/api/v1/households/{home_id}/energy-accounts/{account_id}/meters",
        headers=headers(owner),
        json={"provider_meter_ref": "meter-123"},
    )
    assert meter.status_code == 201
    meter_id = meter.json()["id"]

    assert client.get(
        f"/api/v1/households/{home_id}/energy-accounts/{account_id}/meters",
        headers=headers(member),
    ).status_code == 200
    assert client.get(
        f"/api/v1/households/{home_id}/energy-accounts/{account_id}/meters",
        headers=headers(outsider),
    ).status_code == 404


def test_nested_tariffs_and_readings_cannot_cross_households_or_accounts():
    owner = register("owner@example.com")
    outsider = register("outsider@example.com")
    home_id = household(owner, "Owner home")
    outsider_home_id = household(outsider, "Outsider home")

    account = client.post(
        f"/api/v1/households/{home_id}/energy-accounts",
        headers=headers(owner),
        json={"provider": "octopus", "provider_account_ref": "acc-1"},
    ).json()
    meter = client.post(
        f"/api/v1/households/{home_id}/energy-accounts/{account['id']}/meters",
        headers=headers(owner),
        json={"provider_meter_ref": "meter-1"},
    ).json()

    path = f"/api/v1/households/{outsider_home_id}/energy-accounts/{account['id']}/meters/{meter['id']}/readings"
    assert client.get(path, headers=headers(outsider)).status_code == 404
    assert client.post(
        path,
        headers=headers(outsider),
        json={
            "interval_start": "2026-10-30T00:00:00Z",
            "interval_end": "2026-10-30T00:30:00Z",
            "consumption_kwh": "0.125",
        },
    ).status_code == 404


def test_owner_can_store_tariff_and_reading_with_valid_intervals():
    owner = register("owner@example.com")
    home_id = household(owner, "Test home")
    account = client.post(
        f"/api/v1/households/{home_id}/energy-accounts",
        headers=headers(owner),
        json={"provider": "octopus", "provider_account_ref": "acc-1"},
    ).json()
    meter = client.post(
        f"/api/v1/households/{home_id}/energy-accounts/{account['id']}/meters",
        headers=headers(owner),
        json={"provider_meter_ref": "meter-1"},
    ).json()

    tariff = client.post(
        f"/api/v1/households/{home_id}/energy-accounts/{account['id']}/meters/{meter['id']}/tariffs",
        headers=headers(owner),
        json={
            "tariff_name": "Flexible",
            "valid_from": "2026-10-30T00:00:00Z",
            "standing_charge_p_per_day": "48.5",
            "unit_rate_p_per_kwh": "24.2",
        },
    )
    assert tariff.status_code == 201
    assert tariff.json()["currency"] == "GBP"

    reading_path = f"/api/v1/households/{home_id}/energy-accounts/{account['id']}/meters/{meter['id']}/readings"
    reading = client.post(
        reading_path,
        headers=headers(owner),
        json={
            "interval_start": "2026-10-30T00:00:00Z",
            "interval_end": "2026-10-30T00:30:00Z",
            "consumption_kwh": "0.125",
        },
    )
    assert reading.status_code == 201
    assert client.get(reading_path, headers=headers(owner)).json()[0]["consumption_kwh"] == "0.125"


def test_duplicate_account_and_reading_intervals_are_rejected():
    owner = register("owner@example.com")
    home_id = household(owner, "Test home")
    path = f"/api/v1/households/{home_id}/energy-accounts"
    payload = {"provider": "octopus", "provider_account_ref": "acc-1"}
    assert client.post(path, headers=headers(owner), json=payload).status_code == 201
    assert client.post(path, headers=headers(owner), json=payload).status_code == 409
