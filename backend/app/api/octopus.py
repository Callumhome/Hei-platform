from __future__ import annotations

import base64
import hashlib
import hmac
import re
from datetime import datetime, timezone

import httpx
from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import get_settings
from app.db.models import ConsentGrant, HouseholdMembership, OctopusConnection, User
from app.db.session import get_db

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
    return {"connected": True, "account_last4": item.account_number_last4, "verified_at": item.verified_at}


@router.post("")
async def connect_octopus(household_id: str, payload: OctopusConnectPayload, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _manager(household_id, user, db)
    account = payload.account_number.strip()
    api_key = payload.api_key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,80}", account):
        raise HTTPException(status_code=422, detail="Check the Octopus account number format")
    consent = db.scalar(select(ConsentGrant).where(
        ConsentGrant.household_id == household_id,
        ConsentGrant.provider == "octopus",
        ConsentGrant.status == "granted",
    ).order_by(ConsentGrant.granted_at.desc()))
    if consent is None:
        raise HTTPException(status_code=403, detail="Grant Octopus consent in the Data Permissions section before connecting")
    scopes = set(__import__("json").loads(consent.scopes_json))
    if not {"account_details", "electricity_consumption", "tariff_data"}.issubset(scopes):
        raise HTTPException(status_code=403, detail="Your Octopus consent is missing required permissions")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=False) as client:
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
    return {"connected": True, "account_last4": account[-4:], "property_count": len(account_data.get("properties") or [])}


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
