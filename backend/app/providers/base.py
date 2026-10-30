from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class ElectricityReading:
    meter_identifier: str
    start: datetime
    end: datetime
    consumption_kwh: Decimal
    source: str


class EnergyProvider(ABC):
    """Supplier adapter contract. Implementations must not log credentials or personal data."""

    provider_id: str

    @abstractmethod
    async def validate_connection(self, credentials: dict[str, str]) -> bool:
        """Validate a supplier connection without returning or logging secrets."""
        raise NotImplementedError

    @abstractmethod
    async def get_electricity_readings(
        self,
        credentials: dict[str, str],
        start: datetime,
        end: datetime,
    ) -> list[ElectricityReading]:
        raise NotImplementedError
