from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.config import get_settings
from app.db.models import ConsentGrant, HouseholdMembership, Property, SupplyPoint, User
from app.db.session import get_db
from app.schemas.properties import (
    ConsentCreate, ConsentResponse, PropertyCreate, PropertyResponse,
    SupplyPointCreate, SupplyPointResponse,
)

router = APIRouter(prefix="/households/{household_id}", tags=["properties and consent"])


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


def _property(household_id: str, property_id: str, db: Session) -> Property:
    item = db.scalar(select(Property).where(
        Property.id == property_id, Property.household_id == household_id,
    ))
    if item is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return item


def _key(purpose: bytes) -> bytes:
    secret = get_settings().secret_key.encode("utf-8")
    return base64.urlsafe_b64encode(hashlib.sha256(secret + purpose).digest())


def _masked(fuel: str, last4: str) -> str:
    return ("MPAN" if fuel == "electricity" else "MPRN") + " •••• " + last4


def _consent_response(item: ConsentGrant) -> dict:
    return {
        "id": item.id, "household_id": item.household_id, "property_id": item.property_id,
        "provider": item.provider, "purpose": item.purpose,
        "scopes": json.loads(item.scopes_json), "status": item.status,
        "granted_at": item.granted_at, "expires_at": item.expires_at,
        "revoked_at": item.revoked_at, "created_at": item.created_at,
    }


@router.post("/properties", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
def create_property(household_id: str, payload: PropertyCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db, manager=True)
    item = Property(
        household_id=household_id, property_ref=str(uuid.uuid4()),
        **payload.model_dump(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/properties", response_model=list[PropertyResponse])
def list_properties(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db)
    return db.scalars(select(Property).where(
        Property.household_id == household_id
    ).order_by(Property.created_at, Property.id)).all()


@router.post("/properties/{property_id}/supply-points", response_model=SupplyPointResponse, status_code=status.HTTP_201_CREATED)
def create_supply_point(household_id: str, property_id: str, payload: SupplyPointCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db, manager=True)
    _property(household_id, property_id, db)
    identifier = re.sub(r"\s+", "", payload.identifier)
    if payload.fuel == "electricity" and len(identifier) not in {13, 21}:
        raise HTTPException(status_code=422, detail="An electricity MPAN must be 13 or 21 digits")
    if payload.fuel == "gas" and not 6 <= len(identifier) <= 10:
        raise HTTPException(status_code=422, detail="A gas MPRN must be between 6 and 10 digits")
    digest = hmac.new(_key(b":hei-supply-point-hash:v1"), identifier.encode(), hashlib.sha256).hexdigest()
    encrypted = Fernet(_key(b":hei-supply-point-encryption:v1")).encrypt(identifier.encode()).decode()
    item = SupplyPoint(
        property_id=property_id, fuel=payload.fuel, identifier_encrypted=encrypted,
        identifier_hash=digest, identifier_last4=identifier[-4:],
        supplier_name=payload.supplier_name, status="unverified",
    )
    db.add(item)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        if "uq_supply_point_property_fuel_hash" in str(exc) or "UNIQUE constraint failed" in str(exc):
            raise HTTPException(status_code=409, detail="This supply point is already registered on the property")
        raise
    db.refresh(item)
    return {
        "id": item.id, "property_id": item.property_id, "fuel": item.fuel,
        "identifier_masked": _masked(item.fuel, item.identifier_last4),
        "supplier_name": item.supplier_name, "status": item.status, "created_at": item.created_at,
    }


@router.get("/properties/{property_id}/supply-points", response_model=list[SupplyPointResponse])
def list_supply_points(household_id: str, property_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db)
    _property(household_id, property_id, db)
    items = db.scalars(select(SupplyPoint).where(
        SupplyPoint.property_id == property_id
    ).order_by(SupplyPoint.created_at, SupplyPoint.id)).all()
    return [{
        "id": item.id, "property_id": item.property_id, "fuel": item.fuel,
        "identifier_masked": _masked(item.fuel, item.identifier_last4),
        "supplier_name": item.supplier_name, "status": item.status, "created_at": item.created_at,
    } for item in items]


@router.post("/consents", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
def create_consent(household_id: str, payload: ConsentCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db, manager=True)
    if payload.property_id is not None:
        _property(household_id, payload.property_id, db)
    item = ConsentGrant(
        household_id=household_id, property_id=payload.property_id,
        provider=payload.provider, purpose=payload.purpose,
        scopes_json=json.dumps(payload.scopes), status="pending",
        created_by_user_id=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _consent_response(item)


@router.get("/consents", response_model=list[ConsentResponse])
def list_consents(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db)
    items = db.scalars(select(ConsentGrant).where(
        ConsentGrant.household_id == household_id
    ).order_by(ConsentGrant.created_at.desc(), ConsentGrant.id)).all()
    return [_consent_response(item) for item in items]


@router.post("/consents/{consent_id}/grant", response_model=ConsentResponse)
def grant_consent(household_id: str, consent_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db, manager=True)
    item = db.scalar(select(ConsentGrant).where(
        ConsentGrant.id == consent_id, ConsentGrant.household_id == household_id,
    ))
    if item is None:
        raise HTTPException(status_code=404, detail="Consent record not found")
    if item.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending consent can be granted")
    item.status = "granted"
    item.granted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return _consent_response(item)


@router.post("/consents/{consent_id}/revoke", response_model=ConsentResponse)
def revoke_consent(household_id: str, consent_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user, db, manager=True)
    item = db.scalar(select(ConsentGrant).where(
        ConsentGrant.id == consent_id, ConsentGrant.household_id == household_id,
    ))
    if item is None:
        raise HTTPException(status_code=404, detail="Consent record not found")
    if item.status == "revoked":
        return _consent_response(item)
    item.status = "revoked"
    item.revoked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return _consent_response(item)
