from datetime import datetime, timezone

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.core import rate_limit


def _revocation_key(token_id: str) -> str:
    return f"hei:session:revoked:{token_id}"


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
