"""Airline-neutral flight data. Every provider converts its own API response into FlightStatus."""

from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class Airport:
    code: str  # IATA if known, e.g. "YYZ"
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @property
    def coordinates(self) -> Optional[tuple[float, float]]:
        if self.latitude is not None and self.longitude is not None:
            return self.latitude, self.longitude
        return None


@dataclass
class FlightStatus:
    provider: str  # provider id, e.g. "aircanada"
    airline: str  # display name, e.g. "Air Canada"
    flight_number: str
    origin: Airport
    destination: Airport
    time: datetime  # timestamp from the flight feed (UTC)
    latitude: Optional[float]
    longitude: Optional[float]
    altitude_ft: Optional[float]
    ground_speed_mph: Optional[float]
    vertical_speed: float = 0.0  # > 0 climbing, < 0 descending
    heading: Optional[float] = None  # degrees clockwise from north, if the portal reports it
    aircraft_type: str = ""
    tail_number: str = ""
    departure_time: Optional[datetime] = None
    expected_arrival: Optional[datetime] = None
    minutes_to_land: Optional[int] = None
    phase: str = ""  # e.g. "En Route"
    wifi: str = ""  # free-form connection summary

    @property
    def position(self) -> Optional[tuple[float, float]]:
        if self.latitude is not None and self.longitude is not None:
            return self.latitude, self.longitude
        return None

    @property
    def elapsed_fraction(self) -> Optional[float]:
        """Elapsed share of the time from departure to estimated arrival, 0–1."""
        if self.departure_time and self.expected_arrival:
            duration = (self.expected_arrival - self.departure_time).total_seconds()
            if duration > 0:
                elapsed = (self.time - self.departure_time).total_seconds()
                return max(0.0, min(1.0, elapsed / duration))
        return None

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly dict: datetimes become ISO strings."""
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "FlightStatus":
        known = {f.name for f in fields(cls)}
        d = {k: v for k, v in d.items() if k in known}
        for k in ("time", "departure_time", "expected_arrival"):
            if isinstance(d.get(k), str):
                d[k] = datetime.fromisoformat(d[k])
        d["origin"] = Airport(**d["origin"])
        d["destination"] = Airport(**d["destination"])
        return cls(**d)
