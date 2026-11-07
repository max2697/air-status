"""Data sources, one per airline or in-flight Wi-Fi system.

To add an airline: write a Provider subclass (see aircanada.py, or gogo.py for a
whole Wi-Fi system) and add an instance to PROVIDERS below.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from air_status.providers.aircanada import AirCanada
from air_status.providers.american import American
from air_status.providers.base import Provider

PROVIDERS: dict[str, Provider] = {p.id: p for p in (AirCanada(), American())}
AUTO = "auto"


def detect_provider(providers: Optional[list[Provider]] = None) -> Optional[Provider]:
    """First provider whose portal answers with flight data, or None. Probes all at once."""
    providers = list(PROVIDERS.values()) if providers is None else providers
    if not providers:
        return None
    pool = ThreadPoolExecutor(max_workers=len(providers))
    futures = {pool.submit(p.detect): p for p in providers}
    try:
        for future in as_completed(futures):
            if future.result():
                return futures[future]
        return None
    finally:
        pool.shutdown(wait=False)  # don't wait for slower portals once one answered


def get_provider(provider_id: str) -> Provider:
    try:
        return PROVIDERS[provider_id]
    except KeyError:
        raise ValueError(f"unknown provider {provider_id!r}, choose from: {', '.join(PROVIDERS)}") from None


__all__ = ["AUTO", "PROVIDERS", "Provider", "detect_provider", "get_provider"]
