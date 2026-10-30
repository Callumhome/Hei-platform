from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import get_db
from app.main import app
from app.api import auth as auth_api

sent_tokens = {}
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
    app.dependency_overrides[get_db] = override_get_db
    sent_tokens.clear()
    auth_api.send_verification_email = lambda email, token: sent_tokens.__setitem__(email, token)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def token_for(email: str) -> str:
    assert client.post("/api/v1/auth/register", json={"email": email, "password": "a-very-long-test-password"}).status_code == 202
    assert client.post("/api/v1/auth/verify-email", json={"token": sent_tokens[email]}).status_code == 200
    return client.post("/api/v1/auth/login", json={"email": email, "password": "a-very-long-test-password"}).json()["access_token"]


def headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def household(token: str) -> str:
    return client.post("/api/v1/households", headers=headers(token), json={"name": "Home"}).json()["id"]


def property_payload():
    return {
        "address_line_1": "10 Example Street", "town": "Oxford",
        "postcode": "ox1 1aa", "country_code": "GB",
    }


def test_owner_can_create_and_list_property():
    owner = token_for("owner@example.com")
    hid = household(owner)
    created = client.post(f"/api/v1/households/{hid}/properties", headers=headers(owner), json=property_payload())
    assert created.status_code == 201
    assert created.json()["postcode"] == "OX1 1AA"
    assert client.get(f"/api/v1/households/{hid}/properties", headers=headers(owner)).json()[0]["id"] == created.json()["id"]


def test_property_isolation_and_role_protection():
    owner = token_for("owner@example.com")
    outsider = token_for("outsider@example.com")
    hid = household(owner)
    assert client.post(f"/api/v1/households/{hid}/properties", headers=headers(outsider), json=property_payload()).status_code == 404


def test_supply_point_is_masked_and_duplicate_rejected():
    owner = token_for("owner@example.com")
    hid = household(owner)
    prop = client.post(f"/api/v1/households/{hid}/properties", headers=headers(owner), json=property_payload()).json()
    url = f"/api/v1/households/{hid}/properties/{prop['id']}/supply-points"
    payload = {"fuel": "electricity", "identifier": "1234567890123"}
    first = client.post(url, headers=headers(owner), json=payload)
    assert first.status_code == 201
    assert first.json()["identifier_masked"].endswith("0123")
    assert "1234567890123" not in first.text
    assert client.post(url, headers=headers(owner), json=payload).status_code == 409


def test_consent_requires_explicit_grant_and_can_be_revoked():
    owner = token_for("owner@example.com")
    hid = household(owner)
    created = client.post(
        f"/api/v1/households/{hid}/consents", headers=headers(owner),
        json={"provider": "octopus", "purpose": "Import household electricity readings", "scopes": ["consumption:read", "tariffs:read"]},
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    cid = created.json()["id"]
    granted = client.post(f"/api/v1/households/{hid}/consents/{cid}/grant", headers=headers(owner))
    assert granted.status_code == 200
    assert granted.json()["status"] == "granted"
    revoked = client.post(f"/api/v1/households/{hid}/consents/{cid}/revoke", headers=headers(owner))
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_property_routes_require_authentication():
    response = client.post("/api/v1/households/not-a-household/properties", json=property_payload())
    assert response.status_code == 401
