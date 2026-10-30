from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db.models import Household, HouseholdMembership, User
from app.db.session import get_db
from app.schemas.households import HouseholdCreateRequest, HouseholdResponse

router = APIRouter(prefix="/households", tags=["households"])


def _response(household: Household, role: str) -> HouseholdResponse:
    return HouseholdResponse(
        id=household.id,
        name=household.name,
        country_code=household.country_code,
        timezone=household.timezone,
        role=role,
    )


def _get_membership(
    household_id: str,
    user_id: str,
    db: Session,
) -> tuple[Household, HouseholdMembership]:
    result = db.execute(
        select(Household, HouseholdMembership)
        .join(HouseholdMembership, HouseholdMembership.household_id == Household.id)
        .where(
            Household.id == household_id,
            HouseholdMembership.user_id == user_id,
        )
    ).first()
    if result is None:
        # Return the same response for unknown households and non-members.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household not found")
    return result[0], result[1]


@router.post("", response_model=HouseholdResponse, status_code=status.HTTP_201_CREATED)
def create_household(
    payload: HouseholdCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HouseholdResponse:
    household = Household(
        name=payload.name.strip(),
        country_code=payload.country_code.upper(),
        timezone=payload.timezone,
    )
    if not household.name:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Household name cannot be blank")

    db.add(household)
    db.flush()
    membership = HouseholdMembership(
        household_id=household.id,
        user_id=user.id,
        role="owner",
    )
    db.add(membership)
    db.commit()
    db.refresh(household)
    return _response(household, membership.role)


@router.get("", response_model=list[HouseholdResponse])
def list_households(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[HouseholdResponse]:
    rows = db.execute(
        select(Household, HouseholdMembership.role)
        .join(HouseholdMembership, HouseholdMembership.household_id == Household.id)
        .where(HouseholdMembership.user_id == user.id)
        .order_by(Household.created_at, Household.id)
    ).all()
    return [_response(household, role) for household, role in rows]


@router.get("/{household_id}", response_model=HouseholdResponse)
def read_household(
    household_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HouseholdResponse:
    household, membership = _get_membership(household_id, user.id, db)
    return _response(household, membership.role)
