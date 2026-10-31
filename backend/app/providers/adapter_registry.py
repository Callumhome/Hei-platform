from __future__ import annotations

from app.providers.contracts import ProviderAdapter

_ADAPTERS: dict[str, ProviderAdapter] = {}


def register_adapter(adapter: ProviderAdapter) -> None:
    provider_id = adapter.provider_id.strip().lower()
    if not provider_id or provider_id != adapter.provider_id:
        raise ValueError("provider_id must be a non-empty lowercase identifier")
    if provider_id in _ADAPTERS:
        raise ValueError(f"Provider adapter already registered: {provider_id}")
    _ADAPTERS[provider_id] = adapter


def get_adapter(provider_id: str) -> ProviderAdapter:
    key = provider_id.strip().lower()
    try:
        return _ADAPTERS[key]
    except KeyError as exc:
        raise LookupError(f"Unsupported provider: {key}") from exc


def registered_adapters() -> tuple[str, ...]:
    return tuple(sorted(_ADAPTERS))


def clear_registry() -> None:
    """Clear adapters between isolated tests."""
    _ADAPTERS.clear()
