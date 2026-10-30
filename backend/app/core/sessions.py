import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import rate_limit
from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.models import RefreshSession, User


def _revocation_key(token_id: str) -> str:
    return f"hei:session:revoked:{token_id}"


def _refresh_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired session",
        headers={"WWW-Authenticate": "Bearer"},
    )


def is_token_revoked(token_id: str) -> bool:
    try:
        return bool(rate_limit.get_redis_client().exists(_revocation_key(token_id)))
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication temporarily unavailable",
            headers={"Retry-After": "30"},
        ) from exc


def revoke_token(token_id: str, expires_at: int) -> None:
    now = int(datetime.now(timezone.utc).timestamp())
    ttl = expires_at - now
    if ttl <= 0:
        return
    try:
        rate_limit.get_redis_client().set(_revocation_key(token_id), "1", ex=ttl)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to end session right now",
            headers={"Retry-After": "30"},
        ) from exc


def create_session(db: Session, user: User) -> dict:
    settings = get_settings()
    refresh_token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    session = RefreshSession(
        user_id=user.id,
        token_hash=_refresh_hash(refresh_token),
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()
    return {
        "access_token": create_access_token(user.id, user.token_version, session.id),
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "refresh_expires_in": settings.refresh_token_expire_days * 86400,
    }


def rotate_refresh_token(db: Session, refresh_token: str) -> tuple[User, dict]:
    token_hash = _refresh_hash(refresh_token)
    session = db.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_hash).with_for_update()
    )
    if session is None:
        raise _unauthorized()

    now = datetime.now(timezone.utc)
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    user = db.scalar(select(User).where(User.id == session.user_id))
    if user is None or not user.is_active:
        raise _unauthorized()

    if session.revoked_at is not None:
        db.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        user.token_version += 1
        db.commit()
        raise _unauthorized()

    if expires_at <= now:
        session.revoked_at = now
        db.commit()
        raise _unauthorized()

    settings = get_settings()
    next_token = secrets.token_urlsafe(48)
    next_expires = now + timedelta(days=settings.refresh_token_expire_days)
    next_session = RefreshSession(
        user_id=user.id,
        token_hash=_refresh_hash(next_token),
        expires_at=next_expires,
    )
    db.add(next_session)
    db.flush()
    session.revoked_at = now
    session.replaced_by_id = next_session.id
    db.commit()

    response = {
        "access_token": create_access_token(user.id, user.token_version, next_session.id),
        "refresh_token": next_token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "refresh_expires_in": settings.refresh_token_expire_days * 86400,
    }
    return user, response


def revoke_all_sessions(db: Session, user: User) -> None:
    now = datetime.now(timezone.utc)
    db.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    user.token_version += 1
    db.commit()
