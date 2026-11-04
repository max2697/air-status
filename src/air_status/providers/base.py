from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from air_status.flightlog import FlightHistory
from air_status.models import FlightStatus


class Provider(ABC):
    """One airline or in-flight Wi-Fi system.

    A provider fetches raw readings in its own format, turns them into the shared
    FlightStatus, and decides how its readings are stored in history.
    """

    id: str  # short name used on the command line and as history folder, e.g. "aircanada"
    name: str  # display name, e.g. "Air Canada"
    update_interval: int = 10  # seconds between fresh data at the source

    @abstractmethod
    def fetch(self) -> Any:
        """Current raw reading from the source. Raise on network or format errors."""

    @abstractmethod
    def parse(self, reading: Any) -> FlightStatus:
        """Convert a raw reading into FlightStatus."""

    @abstractmethod
    def history(self, directory: Path) -> FlightHistory:
        """History store for this provider's flights inside `directory`."""
