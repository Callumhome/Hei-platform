from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(subject: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "exp": expires_at,
        "iat": now,
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token_claims(token: str) -> dict | None:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp", "iat", "jti"]},
        )
        subject = payload.get("sub")
        token_id = payload.get("jti")
        if not isinstance(subject, str) or not subject:
            return None
        if not isinstance(token_id, str) or not token_id:
            return None
        return payload
    except jwt.PyJWTError:
        return None


def decode_access_token(token: str) -> str | None:
    claims = decode_access_token_claims(token)
    return claims["sub"] if claims else None
