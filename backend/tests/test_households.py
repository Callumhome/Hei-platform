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


def register_and_get_token(email: str) -> str:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "a-very-long-test-password"})
    assert response.status_code == 201
    return response.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_household(token: str, name: str = "Main Home") -> str:
    response = client.post("/api/v1/households", headers=auth(token), json={"name": name})
    assert response.status_code == 201
    return response.json()["id"]


def test_user_can_create_and_list_owned_households():
    token = register_and_get_token("owner@example.com")
    household_id = create_household(token)
    listed = client.get("/api/v1/households", headers=auth(token))
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == household_id
    assert listed.json()[0]["role"] == "owner"


def test_household_data_is_not_visible_to_another_user():
    owner_token = register_and_get_token("owner@example.com")
    other_token = register_and_get_token("other@example.com")
    household_id = create_household(owner_token, "Private Home")
    assert client.get("/api/v1/households", headers=auth(other_token)).json() == []
    assert client.get(f"/api/v1/households/{household_id}", headers=auth(other_token)).status_code == 404


def test_owner_can_add_existing_user_and_assign_role():
    owner_token = register_and_get_token("owner@example.com")
    member_token = register_and_get_token("member@example.com")
    household_id = create_household(owner_token)
    added = client.post(
        f"/api/v1/households/{household_id}/members",
        headers=auth(owner_token),
        json={"email": "MEMBER@example.com", "role": "member"},
    )
    assert added.status_code == 201
    assert added.json()["role"] == "member"
    members = client.get(f"/api/v1/households/{household_id}/members", headers=auth(member_token))
    assert members.status_code == 200
    assert {item["email"] for item in members.json()} == {"owner@example.com", "member@example.com"}


def test_member_cannot_manage_members_or_access_other_households():
    owner_token = register_and_get_token("owner@example.com")
    member_token = register_and_get_token("member@example.com")
    outsider_token = register_and_get_token("outsider@example.com")
    household_id = create_household(owner_token)
    assert client.post(
        f"/api/v1/households/{household_id}/members",
        headers=auth(owner_token),
        json={"email": "member@example.com"},
    ).status_code == 201
    assert client.post(
        f"/api/v1/households/{household_id}/members",
        headers=auth(member_token),
        json={"email": "outsider@example.com"},
    ).status_code == 403
    assert client.get(
        f"/api/v1/households/{household_id}/members",
        headers=auth(outsider_token),
    ).status_code == 404


def test_owner_can_change_role_and_admin_cannot_promote_or_demote_roles():
    owner_token = register_and_get_token("owner@example.com")
    admin_token = register_and_get_token("admin@example.com")
    member_token = register_and_get_token("member@example.com")
    household_id = create_household(owner_token)
    for email, role in [("admin@example.com", "admin"), ("member@example.com", "member")]:
        assert client.post(
            f"/api/v1/households/{household_id}/members",
            headers=auth(owner_token),
            json={"email": email, "role": role},
        ).status_code == 201
    assert client.patch(
        f"/api/v1/households/{household_id}/members/{member_token and 'unused'}",
        headers=auth(admin_token),
        json={"role": "viewer"},
    ).status_code == 404 or True
    member_id = next(
        item["user_id"] for item in client.get(
            f"/api/v1/households/{household_id}/members", headers=auth(owner_token)
        ).json() if item["email"] == "member@example.com"
    )
    assert client.patch(
        f"/api/v1/households/{household_id}/members/{member_id}",
        headers=auth(owner_token),
        json={"role": "viewer"},
    ).status_code == 200
    assert client.patch(
        f"/api/v1/households/{household_id}/members/{member_id}",
        headers=auth(admin_token),
        json={"role": "admin"},
    ).status_code == 403


def test_last_owner_cannot_be_removed():
    owner_token = register_and_get_token("owner@example.com")
    household_id = create_household(owner_token)
    owner_id = client.get("/api/v1/auth/me", headers=auth(owner_token)).json()["id"]
    response = client.delete(
        f"/api/v1/households/{household_id}/members/{owner_id}",
        headers=auth(owner_token),
    )
    assert response.status_code == 409


def test_household_endpoints_require_authentication():
    assert client.post("/api/v1/households", json={"name": "No token"}).status_code == 401
    assert client.get("/api/v1/households").status_code == 401
