from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.models import Household, HouseholdMembership, User
from app.db.session import get_db
from app.schemas.households import (
    HouseholdCreateRequest,
    HouseholdMemberAddRequest,
    HouseholdMemberResponse,
    HouseholdMemberRoleUpdate,
    HouseholdResponse,
)

router = APIRouter(prefix="/households", tags=["households"])


def _response(household: Household, role: str) -> HouseholdResponse:
    return HouseholdResponse(
        id=household.id,
        name=household.name,
        country_code=household.country_code,
        timezone=household.timezone,
        role=role,
    )


def _get_membership(household_id: str, user_id: str, db: Session) -> tuple[Household, HouseholdMembership]:
    result = db.execute(
        select(Household, HouseholdMembership)
        .join(HouseholdMembership, HouseholdMembership.household_id == Household.id)
        .where(Household.id == household_id, HouseholdMembership.user_id == user_id)
    ).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Household not found")
    return result[0], result[1]


def _require_manager(household_id: str, user: User, db: Session) -> Household:
    household, membership = _get_membership(household_id, user.id, db)
    if membership.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Household owner or admin role required")
    return household


def _member_response(membership: HouseholdMembership) -> HouseholdMemberResponse:
    return HouseholdMemberResponse(
        user_id=membership.user.id,
        email=membership.user.email,
        display_name=membership.user.display_name,
        role=membership.role,
    )


@router.post("", response_model=HouseholdResponse, status_code=status.HTTP_201_CREATED)
def create_household(payload: HouseholdCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> HouseholdResponse:
    household = Household(name=payload.name.strip(), country_code=payload.country_code.upper(), timezone=payload.timezone)
    if not household.name:
        raise HTTPException(status_code=422, detail="Household name cannot be blank")
    db.add(household)
    db.flush()
    membership = HouseholdMembership(household_id=household.id, user_id=user.id, role="owner")
    db.add(membership)
    db.commit()
    db.refresh(household)
    return _response(household, membership.role)


@router.get("", response_model=list[HouseholdResponse])
def list_households(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[HouseholdResponse]:
    rows = db.execute(
        select(Household, HouseholdMembership.role)
        .join(HouseholdMembership, HouseholdMembership.household_id == Household.id)
        .where(HouseholdMembership.user_id == user.id)
        .order_by(Household.created_at, Household.id)
    ).all()
    return [_response(household, role) for household, role in rows]


@router.get("/{household_id}", response_model=HouseholdResponse)
def read_household(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> HouseholdResponse:
    household, membership = _get_membership(household_id, user.id, db)
    return _response(household, membership.role)


@router.get("/{household_id}/members", response_model=list[HouseholdMemberResponse])
def list_household_members(household_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[HouseholdMemberResponse]:
    _get_membership(household_id, user.id, db)
    memberships = db.scalars(
        select(HouseholdMembership)
        .where(HouseholdMembership.household_id == household_id)
        .order_by(HouseholdMembership.created_at, HouseholdMembership.id)
    ).all()
    return [_member_response(item) for item in memberships]


@router.post("/{household_id}/members", response_model=HouseholdMemberResponse, status_code=status.HTTP_201_CREATED)
def add_household_member(household_id: str, payload: HouseholdMemberAddRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> HouseholdMemberResponse:
    _require_manager(household_id, user, db)
    email = payload.email.strip().casefold()
    invited_user = db.scalar(select(User).where(func.lower(User.email) == email))
    if invited_user is None or not invited_user.is_active:
        raise HTTPException(status_code=404, detail="Active registered user not found")
    existing = db.scalar(
        select(HouseholdMembership).where(
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == invited_user.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="User is already a household member")
    membership = HouseholdMembership(household_id=household_id, user_id=invited_user.id, role=payload.role)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return _member_response(membership)


@router.patch("/{household_id}/members/{member_user_id}", response_model=HouseholdMemberResponse)
def update_household_member_role(household_id: str, member_user_id: str, payload: HouseholdMemberRoleUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> HouseholdMemberResponse:
    _, actor_membership = _get_membership(household_id, user.id, db)
    if actor_membership.role != "owner":
        raise HTTPException(status_code=403, detail="Only the household owner can change member roles")
    membership = db.scalar(
        select(HouseholdMembership).where(
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == member_user_id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Household member not found")
    membership.role = payload.role
    db.commit()
    db.refresh(membership)
    return _member_response(membership)


@router.delete("/{household_id}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_household_member(household_id: str, member_user_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    _, actor_membership = _get_membership(household_id, user.id, db)
    target = db.scalar(
        select(HouseholdMembership).where(
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == member_user_id,
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Household member not found")
    if actor_membership.role != "owner" and not (actor_membership.role == "admin" and target.role in {"member", "viewer"}):
        raise HTTPException(status_code=403, detail="Insufficient household permissions")
    if target.role == "owner":
        owner_count = db.scalar(
            select(func.count()).select_from(HouseholdMembership).where(
                HouseholdMembership.household_id == household_id,
                HouseholdMembership.role == "owner",
            )
        )
        if owner_count <= 1:
            raise HTTPException(status_code=409, detail="A household must retain at least one owner")
    db.delete(target)
    db.commit()
