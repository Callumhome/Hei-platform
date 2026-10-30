from __future__ import annotations

import ipaddress
import json
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import get_settings
from app.db.models import HomeAssistantConnection, HouseholdMembership, User
from app.db.session import get_db

router = APIRouter(prefix="/households/{household_id}/home-assistant", tags=["home assistant"])


class ConnectRequest(BaseModel):
    base_url: str = Field(min_length=10, max_length=300)
    token: str = Field(min_length=20, max_length=4096)


def _membership(household_id: str, user: User, db: Session, manager: bool = False):
    membership = db.scalar(select(HouseholdMembership).where(
        HouseholdMembership.household_id == household_id,
        HouseholdMembership.user_id == user.id,
    ))
    if membership is None:
        raise HTTPException(status_code=404, detail="Household not found")
    if manager and membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Household owner or admin role required")
    return membership


def _normalise_url(value: str) -> str:
    parsed = urlsplit(value.strip().rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail="Use a local Home Assistant HTTP or HTTPS address")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        raise HTTPException(status_code=422, detail="For security, use Home Assistant's private IP address")
    if not address.is_private or address.is_loopback or address.is_link_local or address.is_multicast:
        raise HTTPException(status_code=422, detail="Home Assistant address must be on a private network")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail="Enter only the Home Assistant base address")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{address}{port}"


def _fernet() -> Fernet:
    secret = get_settings().secret_key.encode("utf-8")
    key = __import__("base64").urlsafe_b64encode(__import__("hashlib").sha256(secret + b":hei-home-assistant-token:v1").digest())
    return Fernet(key)


def _decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        raise HTTPException(status_code=500, detail="Stored Home Assistant credential cannot be decrypted")


def _client(base_url: str, token: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=False,
        trust_env=False,
    )


def _fetch_states(base_url: str, token: str):
    try:
        with _client(base_url, token) as client:
            response = client.get("/api/states")
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Could not read Home Assistant states. Check the address, token and network access.")


def _energy_entities(states: list[dict]) -> list[dict]:
    results = []
    keywords = ("energy", "power", "electric", "grid", "solar", "pv", "battery", "import", "export", "consumption", "generation", "demand")
    for item in states:
        entity_id = item.get("entity_id", "")
        attrs = item.get("attributes") or {}
        if not entity_id.startswith("sensor."):
            continue
        device_class = attrs.get("device_class")
        state_class = attrs.get("state_class")
        text = entity_id.casefold()
        if device_class not in {"energy", "power"} and not (state_class in {"measurement", "total", "total_increasing"} and any(word in text for word in keywords)):
            continue
        results.append({
            "entity_id": entity_id,
            "name": attrs.get("friendly_name") or entity_id,
            "state": item.get("state"),
            "unit": attrs.get("unit_of_measurement"),
            "device_class": device_class,
            "state_class": state_class,
            "last_updated": item.get("last_updated"),
        })
    return sorted(results, key=lambda item: (item["device_class"] or "", item["name"].casefold()))[:250]


@router.get("")
def connection_status(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db)
    connection = db.scalar(select(HomeAssistantConnection).where(HomeAssistantConnection.household_id == household_id))
    if connection is None:
        return {"connected": False}
    return {"connected": connection.is_active, "base_url": connection.base_url, "last_checked_at": connection.last_checked_at}


@router.post("", status_code=status.HTTP_200_OK)
def connect_home_assistant(household_id: str, payload: ConnectRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db, manager=True)
    base_url = _normalise_url(payload.base_url)
    states = _fetch_states(base_url, payload.token)
    entities = _energy_entities(states)
    if not entities:
        raise HTTPException(status_code=422, detail="Connected successfully, but no energy-related sensor entities were found")
    connection = db.scalar(select(HomeAssistantConnection).where(HomeAssistantConnection.household_id == household_id))
    encrypted = _fernet().encrypt(payload.token.encode()).decode()
    if connection is None:
        connection = HomeAssistantConnection(household_id=household_id, base_url=base_url, token_encrypted=encrypted, is_active=True)
        db.add(connection)
    else:
        connection.base_url = base_url
        connection.token_encrypted = encrypted
        connection.is_active = True
    from datetime import datetime, timezone
    connection.last_checked_at = datetime.now(timezone.utc)
    db.commit()
    return {"connected": True, "base_url": base_url, "entity_count": len(entities), "entities": entities}


@router.get("/entities")
def discover_entities(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db)
    connection = db.scalar(select(HomeAssistantConnection).where(
        HomeAssistantConnection.household_id == household_id,
        HomeAssistantConnection.is_active.is_(True),
    ))
    if connection is None:
        raise HTTPException(status_code=404, detail="Home Assistant is not connected")
    states = _fetch_states(connection.base_url, _decrypt(connection.token_encrypted))
    return {"entities": _energy_entities(states)}


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_home_assistant(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db, manager=True)
    connection = db.scalar(select(HomeAssistantConnection).where(HomeAssistantConnection.household_id == household_id))
    if connection is not None:
        db.delete(connection)
        db.commit()
