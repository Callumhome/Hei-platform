from app.providers.octopus import OctopusEnergyProvider


_PROVIDER_TYPES = {
    "octopus": OctopusEnergyProvider,
}


def available_providers() -> list[str]:
    return sorted(_PROVIDER_TYPES.keys())


def get_provider(provider_id: str):
    provider_type = _PROVIDER_TYPES.get(provider_id)
    if provider_type is None:
        raise ValueError(f"Unknown energy provider: {provider_id}")
    return provider_type()
