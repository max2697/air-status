"""Data sources, one per airline or in-flight Wi-Fi system.

To add an airline: write a Provider subclass (see aircanada.py, or gogo.py for a
whole Wi-Fi system) and add an instance to PROVIDERS below.
"""

from air_status.providers.aircanada import AirCanada
from air_status.providers.base import Provider

PROVIDERS: dict[str, Provider] = {p.id: p for p in (AirCanada(),)}
DEFAULT_PROVIDER = "aircanada"


def get_provider(provider_id: str) -> Provider:
    try:
        return PROVIDERS[provider_id]
    except KeyError:
        raise ValueError(f"unknown provider {provider_id!r}, choose from: {', '.join(PROVIDERS)}") from None


__all__ = ["DEFAULT_PROVIDER", "PROVIDERS", "Provider", "get_provider"]
