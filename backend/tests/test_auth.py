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


def test_register_login_and_authenticated_profile():
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Test.User@example.com",
            "password": "a-very-long-test-password",
            "display_name": "Test User",
        },
    )
    assert registration.status_code == 201
    body = registration.json()
    assert body["user"]["email"] == "test.user@example.com"
    assert "password" not in body["user"]
    token = body["access_token"]

    profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["display_name"] == "Test User"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "TEST.USER@example.com", "password": "a-very-long-test-password"},
    )
    assert login.status_code == 200


def test_duplicate_registration_and_bad_login_are_rejected():
    payload = {"email": "person@example.com", "password": "a-very-long-test-password"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    assert client.post("/api/v1/auth/register", json=payload).status_code == 409
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "incorrect-password"},
    ).status_code == 401


def test_profile_requires_valid_bearer_token():
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalid-token"},
    ).status_code == 401
