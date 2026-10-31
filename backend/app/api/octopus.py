from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import get_settings
from app.db.models import ConsentGrant, HouseholdMembership, OctopusConnection, User
from app.db.session import get_db
from app.services.octopus_sync import (
    octopus_energy_analytics, octopus_sync_status, sync_octopus_household,
)

router = APIRouter(prefix="/households/{household_id}/octopus", tags=["Octopus Energy"])


class OctopusConnectPayload(BaseModel):
    account_number: str = Field(min_length=4, max_length=80)
    api_key: str = Field(min_length=16, max_length=256)


def _key(purpose: bytes) -> bytes:
    secret = get_settings().secret_key.encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(secret + purpose).digest())


def _manager(household_id: str, user: User, db: Session) -> None:
    membership = db.scalar(select(HouseholdMembership).where(
        HouseholdMembership.household_id == household_id,
        HouseholdMembership.user_id == user.id,
    ))
    if membership is None:
        raise HTTPException(status_code=404, detail="Household not found")
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Household owner or admin role required")


@router.get("")
def octopus_status(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _manager(household_id, user, db)
    item = db.scalar(select(OctopusConnection).where(OctopusConnection.household_id == household_id))
    if item is None or not item.is_active:
        return {"connected": False}
    return {
        "connected": True,
        "account_last4": item.account_number_last4,
        "verified_at": item.verified_at,
    }


@router.get("/sync-status")
def octopus_sync_status_route(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _manager(household_id, user, db)
    return octopus_sync_status(db, household_id)


@router.get("/analytics")
def octopus_analytics(
    household_id: str,
    days: int = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _manager(household_id, user, db)
    if not 1 <= days <= 365:
        raise HTTPException(status_code=422, detail="days must be between 1 and 365")
    return octopus_energy_analytics(db, household_id, days)


@router.post("/sync", status_code=202)
def start_octopus_sync(household_id: str, background_tasks: BackgroundTasks, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _manager(household_id, user, db)
    connection = db.scalar(select(OctopusConnection).where(
        OctopusConnection.household_id == household_id,
        OctopusConnection.is_active.is_(True),
    ))
    if connection is None:
        raise HTTPException(status_code=404, detail="Octopus is not connected")
    latest = octopus_sync_status(db, household_id)
    if latest["status"] == "running":
        return {"queued": False, "status": "running", "message": "An Octopus import is already running."}
    background_tasks.add_task(sync_octopus_household, household_id)
    return {"queued": True, "status": "queued", "message": "Octopus historical import and refresh have been queued."}


@router.post("")
async def connect_octopus(
    household_id: str,
    payload: OctopusConnectPayload,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _manager(household_id, user, db)
    account = payload.account_number.strip()
    api_key = payload.api_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}", account):
        raise HTTPException(status_code=422, detail="Check the Octopus account number format")
    consent = db.scalar(select(ConsentGrant).where(
        ConsentGrant.household_id == household_id,
        ConsentGrant.provider == "octopus",
    ).order_by(ConsentGrant.created_at.desc(), ConsentGrant.id.desc()))
    if consent is None or consent.status != "granted":
        raise HTTPException(status_code=403, detail="Grant the latest Octopus consent in the Data Permissions section before connecting")
    scopes = set(json.loads(consent.scopes_json))
    if not {"account_details", "electricity_consumption", "tariff_data"}.issubset(scopes):
        raise HTTPException(status_code=403, detail="Your Octopus consent is missing required permissions")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=False, trust_env=False) as client:
            response = await client.get(
                "https://api.octopus.energy/v1/accounts/" + account + "/",
                auth=httpx.BasicAuth(api_key, ""),
            )
        if response.status_code == 401:
            raise HTTPException(status_code=401, detail="Octopus rejected the API key. Check it and try again.")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Octopus account number was not found.")
        response.raise_for_status()
        account_data = response.json()
        if not isinstance(account_data, dict) or not account_data.get("number"):
            raise ValueError("Unexpected account response")
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError):
        raise HTTPException(status_code=502, detail="Couldn't verify the Octopus account right now. Please try again.")
    account_hash = hmac.new(_key(b":hei-octopus-account-hash:v1"), account.encode(), hashlib.sha256).hexdigest()
    encrypt = Fernet(_key(b":hei-octopus-credentials:v1"))
    item = db.scalar(select(OctopusConnection).where(OctopusConnection.household_id == household_id))
    values = {
        "account_number_encrypted": encrypt.encrypt(account.encode()).decode(),
        "account_number_last4": account[-4:],
        "account_number_hash": account_hash,
        "api_key_encrypted": encrypt.encrypt(api_key.encode()).decode(),
        "is_active": True,
        "verified_at": datetime.now(timezone.utc),
    }
    if item is None:
        item = OctopusConnection(household_id=household_id, **values)
        db.add(item)
    else:
        for key, value in values.items():
            setattr(item, key, value)
    db.commit()
    # Start the first full history import after credentials have been committed.
    background_tasks.add_task(sync_octopus_household, household_id)
    return {
        "connected": True,
        "account_last4": account[-4:],
        "property_count": len(account_data.get("properties") or []),
        "sync_queued": True,
    }


@router.delete("")
def disconnect_octopus(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _manager(household_id, user, db)
    item = db.scalar(select(OctopusConnection).where(OctopusConnection.household_id == household_id))
    if item is not None:
        item.is_active = False
        item.account_number_encrypted = ""
        item.api_key_encrypted = ""
        db.commit()
    return {"connected": False}
