import pytest


class InMemoryRedis:
    """Deterministic Redis substitute for tests; production always uses Redis."""

    def __init__(self):
        self.counts = {}

    def eval(self, script, number_of_keys, key, window_seconds):
        count = self.counts.get(key, 0) + 1
        self.counts[key] = count
        return [count, window_seconds]


@pytest.fixture(autouse=True)
def fake_rate_limit_redis(monkeypatch):
    from app.core import rate_limit

    client = InMemoryRedis()
    monkeypatch.setattr(rate_limit, "get_redis_client", lambda: client)
    return client
