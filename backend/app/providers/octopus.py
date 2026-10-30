from datetime import datetime

from app.providers.base import ElectricityReading, EnergyProvider


class OctopusEnergyProvider(EnergyProvider):
    """Placeholder for the first supplier integration.

    Real account linking and API calls are deliberately not implemented yet.
    Do not pass live account credentials to this class until secure credential
    storage, consent, and authorization flows have been implemented.
    """

    provider_id = "octopus"

    async def validate_connection(self, credentials: dict[str, str]) -> bool:
        raise NotImplementedError("Octopus account linking is not implemented yet")

    async def get_electricity_readings(
        self,
        credentials: dict[str, str],
        start: datetime,
        end: datetime,
    ) -> list[ElectricityReading]:
        raise NotImplementedError("Octopus consumption ingestion is not implemented yet")
