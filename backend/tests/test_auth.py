import jwt
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import auth as auth_api
from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db import models  # noqa: F401
from app.db.base import Base
from app.db.models import User
from app.db.session import get_db
from app.main import app

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


def register(email):
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "a-very-long-test-password"})
    if response.status_code == 202:
        assert client.post("/api/v1/auth/verify-email", json={"token": sent_tokens[email]}).status_code == 200
    return response


def login(email, password="a-very-long-test-password"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_registration_requires_verification_and_then_login_works():
    payload = {"email": "person@example.com", "password": "a-very-long-test-password", "display_name": "Person"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 202
    assert login("person@example.com").status_code == 403
    token = sent_tokens["person@example.com"]
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
    authenticated = login("person@example.com")
    assert authenticated.status_code == 200
    assert authenticated.json()["user"]["email_verified"] is True
    profile = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {authenticated.json()['access_token']}"})
    assert profile.status_code == 200


def test_duplicate_registration_and_bad_login():
    assert register("duplicate@example.com").status_code == 202
    assert client.post("/api/v1/auth/register", json={"email": "duplicate@example.com", "password": "a-very-long-test-password"}).status_code == 409
    assert login("duplicate@example.com", "wrong-password").status_code == 401


def test_resend_replaces_previous_verification_link_and_does_not_disclose_unknown_accounts():
    client.post("/api/v1/auth/register", json={"email": "resend@example.com", "password": "a-very-long-test-password"})
    old = sent_tokens["resend@example.com"]
    response = client.post("/api/v1/auth/resend-verification", json={"email": "resend@example.com"})
    new = sent_tokens["resend@example.com"]
    assert response.status_code == 202 and new != old
    assert client.post("/api/v1/auth/verify-email", json={"token": old}).status_code == 400
    assert client.post("/api/v1/auth/verify-email", json={"token": new}).status_code == 200
    unknown = client.post("/api/v1/auth/resend-verification", json={"email": "unknown@example.com"})
    assert unknown.status_code == 202 and unknown.json() == response.json()


def test_invalid_bearer_and_missing_claims_are_rejected():
    settings = get_settings()
    no_exp = jwt.encode({"sub": "user", "iat": datetime.now(timezone.utc)}, settings.secret_key, algorithm="HS256")
    no_iat = jwt.encode({"sub": "user", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, settings.secret_key, algorithm="HS256")
    assert decode_access_token(no_exp) is None and decode_access_token(no_iat) is None
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad"}).status_code == 401


def test_inactive_user_cannot_use_token():
    register("inactive@example.com")
    token = login("inactive@example.com").json()["access_token"]
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "inactive@example.com").one()
    user.is_active = False
    db.commit()
    db.close()
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_registration_and_login_rate_limits():
    for i in range(5):
        assert client.post("/api/v1/auth/register", json={"email": f"rate{i}@example.com", "password": "a-very-long-test-password"}).status_code == 202
    assert client.post("/api/v1/auth/register", json={"email": "rate-final@example.com", "password": "a-very-long-test-password"}).status_code == 429
    register("login-limit@example.com")
    for _ in range(8):
        assert login("login-limit@example.com", "wrong-password").status_code == 401
    assert login("login-limit@example.com", "wrong-password").status_code == 429


def test_logout_and_refresh_replay_revoke_sessions():
    register("sessions@example.com")
    first = login("sessions@example.com").json()
    second = login("sessions@example.com").json()
    rotated = client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert rotated.status_code == 200
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {first['access_token']}"}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {rotated.json()['access_token']}"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {second['access_token']}"}).status_code == 401


def test_logout_all_invalidates_every_device():
    register("all@example.com")
    one = login("all@example.com").json()
    two = login("all@example.com").json()
    result = client.post("/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {one['access_token']}"})
    assert result.status_code == 200
    for token in (one["access_token"], two["access_token"]):
        assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": two["refresh_token"]}).status_code == 401
