from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db import models  # noqa: F401
from app.db.session import get_db
from app.main import app

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
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


def register_and_get_token(email: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-very-long-test-password"},
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_user_can_create_and_list_owned_households():
    token = register_and_get_token("owner@example.com")
    created = client.post(
        "/api/v1/households",
        headers=auth(token),
        json={"name": "Main Home"},
    )
    assert created.status_code == 201
    household = created.json()
    assert household["name"] == "Main Home"
    assert household["country_code"] == "GB"
    assert household["timezone"] == "Europe/London"
    assert household["role"] == "owner"

    listed = client.get("/api/v1/households", headers=auth(token))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [household["id"]]


def test_household_data_is_not_visible_to_another_user():
    owner_token = register_and_get_token("owner@example.com")
    other_token = register_and_get_token("other@example.com")
    created = client.post(
        "/api/v1/households",
        headers=auth(owner_token),
        json={"name": "Private Home"},
    )
    household_id = created.json()["id"]

    assert client.get("/api/v1/households", headers=auth(other_token)).json() == []
    denied = client.get(f"/api/v1/households/{household_id}", headers=auth(other_token))
    assert denied.status_code == 404


def test_household_endpoints_require_authentication():
    assert client.post("/api/v1/households", json={"name": "No token"}).status_code == 401
    assert client.get("/api/v1/households").status_code == 401
