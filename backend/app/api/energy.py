from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.models import ElectricityReading, EnergyAccount, HouseholdMembership, Meter, Tariff, User
from app.db.session import get_db
from app.schemas.energy import (
    ElectricityReadingCreate, ElectricityReadingResponse, EnergyAccountCreate,
    EnergyAccountResponse, MeterCreate, MeterResponse, TariffCreate, TariffResponse,
)

router = APIRouter(prefix="/households/{household_id}/energy-accounts", tags=["household energy"])


def _membership(household_id: str, user_id: str, db: Session) -> HouseholdMembership:
    membership = db.scalar(select(HouseholdMembership).where(
        HouseholdMembership.household_id == household_id,
        HouseholdMembership.user_id == user_id,
    ))
    if membership is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return membership


def _manager(household_id: str, user: User, db: Session) -> HouseholdMembership:
    membership = _membership(household_id, user.id, db)
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Household owner or admin role required")
    return membership


def _account(household_id: str, account_id: str, db: Session) -> EnergyAccount:
    account = db.scalar(select(EnergyAccount).where(
        EnergyAccount.id == account_id, EnergyAccount.household_id == household_id,
    ))
    if account is None:
        raise HTTPException(status_code=404, detail="Energy account not found")
    return account


def _meter(household_id: str, meter_id: str, db: Session) -> Meter:
    meter = db.scalar(
        select(Meter).join(EnergyAccount, Meter.energy_account_id == EnergyAccount.id)
        .where(Meter.id == meter_id, EnergyAccount.household_id == household_id)
    )
    if meter is None:
        raise HTTPException(status_code=404, detail="Meter not found")
    return meter


@router.post("", response_model=EnergyAccountResponse, status_code=status.HTTP_201_CREATED)
def create_energy_account(household_id: str, payload: EnergyAccountCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _manager(household_id, user, db)
    account = EnergyAccount(household_id=household_id, **payload.model_dump())
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This provider account is already registered in the household")
    db.refresh(account)
    return account


@router.get("", response_model=list[EnergyAccountResponse])
def list_energy_accounts(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user.id, db)
    return db.scalars(select(EnergyAccount).where(
        EnergyAccount.household_id == household_id
    ).order_by(EnergyAccount.linked_at, EnergyAccount.id)).all()


@router.post("/{account_id}/meters", response_model=MeterResponse, status_code=status.HTTP_201_CREATED)
def create_meter(household_id: str, account_id: str, payload: MeterCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _manager(household_id, user, db)
    account = _account(household_id, account_id, db)
    meter = Meter(energy_account_id=account.id, **payload.model_dump())
    db.add(meter)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This meter is already registered on the account")
    db.refresh(meter)
    return meter


@router.get("/{account_id}/meters", response_model=list[MeterResponse])
def list_meters(household_id: str, account_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user.id, db)
    account = _account(household_id, account_id, db)
    return db.scalars(select(Meter).where(Meter.energy_account_id == account.id).order_by(Meter.id)).all()


@router.post("/{account_id}/meters/{meter_id}/tariffs", response_model=TariffResponse, status_code=status.HTTP_201_CREATED)
def create_tariff(household_id: str, account_id: str, meter_id: str, payload: TariffCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _manager(household_id, user, db)
    account = _account(household_id, account_id, db)
    meter = _meter(household_id, meter_id, db)
    if meter.energy_account_id != account.id:
        raise HTTPException(status_code=404, detail="Meter not found on this account")
    tariff = Tariff(meter_id=meter.id, **payload.model_dump())
    db.add(tariff)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This tariff conflicts with an existing database constraint")
    db.refresh(tariff)
    return tariff


@router.get("/{account_id}/meters/{meter_id}/tariffs", response_model=list[TariffResponse])
def list_tariffs(household_id: str, account_id: str, meter_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _membership(household_id, user.id, db)
    account = _account(household_id, account_id, db)
    meter = _meter(household_id, meter_id, db)
    if meter.energy_account_id != account.id:
        raise HTTPException(status_code=404, detail="Meter not found on this account")
    return db.scalars(select(Tariff).where(Tariff.meter_id == meter.id).order_by(Tariff.valid_from)).all()


@router.post("/{account_id}/meters/{meter_id}/readings", response_model=ElectricityReadingResponse, status_code=status.HTTP_201_CREATED)
def create_reading(household_id: str, account_id: str, meter_id: str, payload: ElectricityReadingCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _manager(household_id, user, db)
    account = _account(household_id, account_id, db)
    meter = _meter(household_id, meter_id, db)
    if meter.energy_account_id != account.id:
        raise HTTPException(status_code=404, detail="Meter not found on this account")
    reading = ElectricityReading(meter_id=meter.id, **payload.model_dump())
    db.add(reading)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A reading already exists for this meter interval")
    db.refresh(reading)
    return reading


@router.get("/{account_id}/meters/{meter_id}/readings", response_model=list[ElectricityReadingResponse])
def list_readings(
    household_id: str,
    account_id: str,
    meter_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _membership(household_id, user.id, db)
    account = _account(household_id, account_id, db)
    meter = _meter(household_id, meter_id, db)
    if meter.energy_account_id != account.id:
        raise HTTPException(status_code=404, detail="Meter not found on this account")
    statement = (
        select(ElectricityReading)
        .where(ElectricityReading.meter_id == meter.id)
        .order_by(ElectricityReading.interval_start, ElectricityReading.id)
        .offset(offset)
        .limit(limit)
    )
    return db.scalars(statement).all()
