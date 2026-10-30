from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token_claims, hash_password, verify_password
from app.core.sessions import (
    create_session,
    is_token_revoked,
    revoke_all_sessions,
    revoke_token,
    rotate_refresh_token,
)
from app.core.rate_limit import enforce_rate_limit
from app.db.models import RefreshSession, User
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["authentication"])
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    claims = decode_access_token_claims(credentials.credentials)
    if claims is None or is_token_revoked(claims["jti"]):
        raise unauthorized
    user = db.scalar(select(User).where(User.id == claims["sub"]))
    session = db.scalar(
        select(RefreshSession).where(
            RefreshSession.id == claims["sid"],
            RefreshSession.user_id == claims["sub"],
        )
    )
    if (
        user is None
        or not user.is_active
        or user.token_version != claims["ver"]
        or session is None
        or session.revoked_at is not None
    ):
        raise unauthorized
    return user


def _token_response(user: User, db: Session) -> TokenResponse:
    credentials = create_session(db, user)
    return TokenResponse(
        **credentials,
        user=UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
        ),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    enforce_rate_limit(
        request,
        action="register",
        identifier="registration",
        limit=5,
        window_seconds=3600,
    )
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to create account with these details")
    return _token_response(user, db)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    enforce_rate_limit(
        request,
        action="login-ip",
        identifier="all",
        limit=30,
        window_seconds=900,
    )
    enforce_rate_limit(
        request,
        action="login-account",
        identifier=payload.email,
        limit=8,
        window_seconds=900,
    )
    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_response(user, db)


@router.post("/refresh", response_model=TokenResponse)
def refresh_access_token(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user, credentials = rotate_refresh_token(db, payload.refresh_token)
    return TokenResponse(
        **credentials,
        user=UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            is_active=user.is_active,
        ),
    )


@router.get("/me", response_model=UserResponse)
def read_current_user(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
    )


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_access_token_claims(credentials.credentials)
    if claims is None or claims["sub"] != user.id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    revoke_token(claims["jti"], int(claims["exp"]))
    session = db.scalar(select(RefreshSession).where(RefreshSession.id == claims["sid"]))
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return {"message": "Session ended"}


@router.post("/logout-all")
def logout_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    revoke_all_sessions(db, user)
    return {"message": "All sessions ended"}
