from __future__ import annotations

from app.providers.contracts import ProviderCapabilities, ReadingPage


class FakeProvider:
    """Deterministic test adapter. It performs no network access."""

    provider_id = "fake"
    capabilities = ProviderCapabilities(
        fuels=frozenset({"electricity", "gas"}),
        supports_interval_readings=True,
        supports_tariffs=True,
        supports_pagination=True,
    )

    def __init__(self, pages: dict[str | None, ReadingPage] | None = None):
        self.pages = pages or {None: ReadingPage(readings=())}
        self.calls: list[tuple[str, str | None, int]] = []

    async def fetch_readings(self, meter_ref: str, *, cursor: str | None = None, page_size: int = 100) -> ReadingPage:
        if not 1 <= page_size <= 500:
            raise ValueError("page_size must be between 1 and 500")
        self.calls.append((meter_ref, cursor, page_size))
        return self.pages.get(cursor, ReadingPage(readings=()))
