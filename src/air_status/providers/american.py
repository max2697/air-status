"""American Airlines Wi-Fi portal (aainflight.com) on Viasat aircraft.

The Viasat flight feed gives position and ICAO airport codes but no airport
locations, so those come from the portal's ground API (by IATA code) once per
airport and are stored with each reading.
"""

import json
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from air_status.flightlog import ChangeLog
from air_status.models import Airport, FlightStatus
from air_status.providers.base import Provider

Raw = dict[str, Any]

BASE_URL = "https://www.aainflight.com/api/v1"
KNOTS_TO_MPH = 1.15078  # groundspeed is in knots (checked against position changes)
# The feed has no vertical speed, so it's worked out from altitude changes over a
# window long enough to smooth out the ±10 ft jitter between readings.
CLIMB_WINDOW = 60  # seconds of altitude readings kept
CLIMB_MIN_SPAN = 15  # seconds needed before a vertical speed is given

# ICAO prefixes where the IATA code is the last three letters (US, Canada, Alaska/Hawaii)
SIMPLE_ICAO_PREFIXES = ("K", "C", "PA", "PH")


def icao_to_iata(icao: str) -> Optional[str]:
    """'KDFW' -> 'DFW'. None where the codes are unrelated (e.g. EGLL/LHR)."""
    if len(icao) == 4 and icao.startswith(SIMPLE_ICAO_PREFIXES):
        return icao[1:]
    return None


def parse_time(value: Optional[str]) -> Optional[datetime]:
    """'2026-01-15T18:00:43Z' -> aware UTC datetime."""
    if not value:
        return None
    return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def _degrees(c: Raw, hemi_key: str) -> float:
    value = c["geographicDegrees"] + c.get("geographicMinute", 0) / 60 + c.get("geographicSeconds", 0) / 3600
    return -value if c.get(hemi_key) in ("S", "W") else value


def airport_from_ground(data: Raw) -> Raw:
    """Ground API airport response -> {'iata', 'latitude', 'longitude'}."""
    details = data["airport"]["locationDetails"]
    coords = details["airportCoordinates"]
    return {
        "iata": details["basicAirportInformation"]["code"],
        "latitude": round(_degrees(coords["airportLatitudeCoordinates"], "latitudeHemiCode"), 5),
        "longitude": round(_degrees(coords["airportLongitudeCoordinates"], "longitudeHemiCode"), 5),
    }


def _get(path: str) -> Any:
    with urllib.request.urlopen(f"{BASE_URL}/{path}", timeout=10) as resp:
        return json.load(resp)


class AmericanHistory(ChangeLog):
    """Stores the Viasat flight data, the route's airports and the satellite link state."""

    def __init__(self, directory: Path, provider: "American"):
        super().__init__(directory)
        self.provider = provider

    def path_for(self, reading: Raw) -> Path:
        f = reading["flight"]
        # flightId looks like '<tail>_SF_<YYYYMMDDhhmmss>'; its date stays the same past midnight
        stamp = (f.get("flightId") or "").rsplit("_", 1)[-1]
        day = f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}" if len(stamp) >= 8 and stamp.isdigit() else f["timestamp"][:10]
        airports = reading.get("airports") or {}
        frm = (airports.get(f["origin"]) or {}).get("iata") or f["origin"]
        to = (airports.get(f["destination"]) or {}).get("iata") or f["destination"]
        return self.directory / f"{day}_{f.get('flightNumber') or 'unknown'}_{frm}-{to}{self.suffix}"

    def to_record(self, reading: Raw) -> Raw:
        return reading  # fetch() already leaves out the device and timestamps that change every call

    def from_record(self, record: Raw) -> FlightStatus:
        return self.provider.parse(record)


class American(Provider):
    id = "american"
    name = "American Airlines"
    update_interval = 6  # measured: the feed's timestamp moves every 6–8 s

    def __init__(self) -> None:
        self._airports: dict[str, Raw] = {}  # ICAO -> airport record, fetched once per run
        self._altitudes: deque[tuple[datetime, float]] = deque()  # recent (time, altitude ft)
        self._flight_id: Optional[str] = None

    def _vertical_speed(self, flight: Raw) -> Optional[float]:
        """Feet per second over the last CLIMB_WINDOW seconds, None until enough readings."""
        time, altitude = parse_time(flight.get("timestamp")), flight.get("altitude")
        if time is None or not isinstance(altitude, (int, float)):
            return None
        if flight.get("flightId") != self._flight_id:
            self._altitudes.clear()
            self._flight_id = flight.get("flightId")
        if not self._altitudes or self._altitudes[-1][0] < time:
            self._altitudes.append((time, altitude))
        while (time - self._altitudes[0][0]).total_seconds() > CLIMB_WINDOW:
            self._altitudes.popleft()
        start_time, start_alt = self._altitudes[0]
        span = (time - start_time).total_seconds()
        return round((altitude - start_alt) / span, 1) if span >= CLIMB_MIN_SPAN else None

    def _airport(self, icao: str) -> Raw:
        if icao not in self._airports:
            iata = icao_to_iata(icao)
            if iata is None:
                raise ValueError(f"no IATA code known for airport {icao}")
            try:
                self._airports[icao] = airport_from_ground(_get(f"ground/api/v1/airports/{iata}"))
            except (urllib.error.URLError, KeyError, TypeError) as e:
                raise ValueError(f"airport {iata} lookup failed: {e}") from e
        return self._airports[icao]

    def fetch(self) -> Raw:
        flight = _get("connectivity/viasat/flight")
        reading: Raw = {
            "flight": flight,
            "airports": {code: self._airport(code) for code in (flight["origin"], flight["destination"])},
        }
        vs = self._vertical_speed(flight)
        if vs is not None:
            reading["climb"] = {"verticalSpeed": vs}  # ft/s, worked out here, not from the portal
        try:
            services = _get("connectivity/viasat/services")
            sat = next((s for s in services.get("serviceList", []) if s.get("serviceName") == "satelliteNetwork"), {})
            details = sat.get("details") or {}
            reading["satellite"] = {"state": sat.get("serviceState"), "band": details.get("frequencyBand")}
        except (OSError, ValueError):
            pass  # link status is extra; the flight data is what matters
        return reading

    def history(self, directory: Path) -> AmericanHistory:
        return AmericanHistory(directory, self)

    def parse(self, raw: Raw) -> FlightStatus:
        f = raw["flight"]
        airports = raw["airports"]
        o, d = airports[f["origin"]], airports[f["destination"]]
        time = parse_time(f["timestamp"])
        to_go = f.get("timeToGo")
        arrival = time + timedelta(minutes=to_go) if time and to_go is not None else None
        duration = f.get("flightDuration")
        sat = raw.get("satellite") or {}
        heading = f.get("heading")  # -180..180
        return FlightStatus(
            provider=self.id,
            airline=self.name,
            flight_number=f.get("flightNumber") or "",
            origin=Airport(o["iata"], o["latitude"], o["longitude"]),
            destination=Airport(d["iata"], d["latitude"], d["longitude"]),
            time=time,
            latitude=f["latitude"],
            longitude=f["longitude"],
            altitude_ft=f["altitude"],
            ground_speed_mph=(f.get("groundspeed") or 0) * KNOTS_TO_MPH,
            vertical_speed=(raw.get("climb") or {}).get("verticalSpeed") or 0.0,
            heading=heading % 360 if isinstance(heading, (int, float)) else None,
            tail_number=f.get("vehicleId") or "",
            departure_time=arrival - timedelta(minutes=duration) if arrival and duration else None,
            expected_arrival=arrival,
            minutes_to_land=to_go,
            phase=f.get("flightPhase") or "",
            wifi=" · ".join(x for x in (sat.get("state"), sat.get("band")) if x),
        )
