import hashlib
from functools import lru_cache

from fastapi import HTTPException, Request, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


@lru_cache
def get_redis_client() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


def _key(action: str, identifier: str) -> str:
    digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()
    return f"hei:rate-limit:{action}:{digest}"


def enforce_rate_limit(
    request: Request,
    *,
    action: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Apply an atomic Redis fixed-window limit; fail closed if Redis is unavailable."""
    client_ip = request.client.host if request.client else "unknown"
    key = _key(action, f"{client_ip}:{identifier}")
    try:
        count, ttl = get_redis_client().eval(_RATE_LIMIT_SCRIPT, 1, key, window_seconds)
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication temporarily unavailable",
            headers={"Retry-After": "30"},
        ) from exc

    if int(count) > limit:
        retry_after = max(1, int(ttl))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
