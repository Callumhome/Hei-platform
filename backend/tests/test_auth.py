import jwt
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db import models  # noqa: F401
from app.core.config import get_settings
from app.core.security import decode_access_token
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
    # Other test modules also override this app-wide dependency during import.
    # Reassert this module's isolated database before each auth test.
    app.dependency_overrides[get_db] = override_get_db
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


def test_access_token_requires_expiry_and_issued_at_claims():
    settings = get_settings()
    token_without_expiry = jwt.encode(
        {"sub": "user-id", "iat": datetime.now(timezone.utc)},
        settings.secret_key,
        algorithm="HS256",
    )
    token_without_issued_at = jwt.encode(
        {"sub": "user-id", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.secret_key,
        algorithm="HS256",
    )
    assert decode_access_token(token_without_expiry) is None
    assert decode_access_token(token_without_issued_at) is None


def test_inactive_user_cannot_use_an_existing_access_token():
    from app.db.models import User

    registration = client.post(
        "/api/v1/auth/register",
        json={"email": "inactive@example.com", "password": "a-very-long-test-password"},
    )
    assert registration.status_code == 201
    token = registration.json()["access_token"]
    db = TestingSessionLocal()
    try:
        user = db.query(User).filter(User.email == "inactive@example.com").one()
        user.is_active = False
        db.commit()
    finally:
        db.close()
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
