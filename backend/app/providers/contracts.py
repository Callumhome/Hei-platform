from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ProviderCapabilities:
    fuels: frozenset[str]
    supports_interval_readings: bool = False
    supports_tariffs: bool = False
    supports_pagination: bool = False


@dataclass(frozen=True)
class NormalizedReading:
    """Interval energy in kWh. This is not instantaneous power in watts."""
    interval_start: datetime
    interval_end: datetime
    import_kwh: Decimal
    export_kwh: Decimal = Decimal("0")
    quality: str = "actual"
    source_record_ref: str | None = None

    def validate(self) -> None:
        for name, value in (("interval_start", self.interval_start), ("interval_end", self.interval_end)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must include a timezone")
        if self.interval_end <= self.interval_start:
            raise ValueError("interval_end must be later than interval_start")
        if self.import_kwh < 0 or self.export_kwh < 0:
            raise ValueError("Import and export energy must be non-negative")
        if self.quality not in {"actual", "estimated", "corrected", "unknown"}:
            raise ValueError("Unsupported reading quality")


@dataclass(frozen=True)
class ReadingPage:
    readings: tuple[NormalizedReading, ...]
    next_cursor: str | None = None


@runtime_checkable
class ProviderAdapter(Protocol):
    provider_id: str
    capabilities: ProviderCapabilities

    async def fetch_readings(
        self, meter_ref: str, *, cursor: str | None = None, page_size: int = 100
    ) -> ReadingPage: ...
