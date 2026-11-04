"""Airline-neutral flight data. Every provider converts its own API response into FlightStatus."""

from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class Airport:
    code: str  # IATA if known, e.g. "YYZ"
    latitude: float
    longitude: float


@dataclass
class FlightStatus:
    provider: str  # provider id, e.g. "aircanada"
    airline: str  # display name, e.g. "Air Canada"
    flight_number: str
    origin: Airport
    destination: Airport
    time: datetime  # when the aircraft produced this reading (UTC)
    latitude: float
    longitude: float
    altitude_ft: float
    ground_speed_mph: float
    vertical_speed: float = 0.0  # > 0 climbing, < 0 descending
    aircraft_type: str = ""
    tail_number: str = ""
    departure_time: Optional[datetime] = None
    expected_arrival: Optional[datetime] = None
    minutes_to_land: Optional[int] = None
    phase: str = ""  # e.g. "En Route"
    wifi: str = ""  # free-form connection summary

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
