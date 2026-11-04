"""Gogo / Intelsat in-flight Wi-Fi portal (statusTray API), used by several airlines."""

import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from air_status.flightlog import ChangeLog
from air_status.models import Airport, FlightStatus
from air_status.providers.base import Provider

Raw = dict[str, Any]

# Left out of history: your device (privacy), trivia text, and copies of flightInfo fields
NOT_SAVED = {
    "top": ("ipAddress", "macAddress", "device_iid", "gogoFacts"),
    "systemInfo": ("horizontalVelocity", "verticalVelocity", "aboveGndLevel"),
}


def parse_time(value: Optional[str]) -> Optional[datetime]:
    """'2026-01-15T21:03:00.00Z' -> aware UTC datetime (fraction ignored)."""
    if not value:
        return None
    return datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class GogoHistory(ChangeLog):
    """Stores the raw portal response (change-only), so no Gogo field is lost."""

    def __init__(self, directory: Path, provider: "GogoProvider"):
        super().__init__(directory)
        self.provider = provider

    def path_for(self, reading: Raw) -> Path:
        f = reading["flightInfo"]
        day = (f.get("departureTime") or f["utcTime"])[:10]
        frm = f.get("departureAirportCodeIata") or f["departureAirportCode"]
        to = f.get("destinationAirportCodeIata") or f["destinationAirportCode"]
        return self.directory / f"{day}_{f.get('flightNumberInfo') or 'unknown'}_{frm}-{to}{self.suffix}"

    def to_record(self, reading: Raw) -> Raw:
        record = {k: v for k, v in reading.items() if k not in NOT_SAVED["top"]}
        if isinstance(record.get("systemInfo"), dict):
            record["systemInfo"] = {k: v for k, v in record["systemInfo"].items() if k not in NOT_SAVED["systemInfo"]}
        return record

    def from_record(self, record: Raw) -> FlightStatus:
        return self.provider.parse(record)


class GogoProvider(Provider):
    url = "https://wifi.inflightinternet.com/abp/v2/statusTray"
    update_interval = 10  # measured: the portal refreshes position every 10 s

    def fetch(self) -> Raw:
        with urllib.request.urlopen(self.url, timeout=10) as resp:
            return json.load(resp)["Response"]

    def history(self, directory: Path) -> GogoHistory:
        return GogoHistory(directory, self)

    def parse(self, raw: Raw) -> FlightStatus:
        f = raw["flightInfo"]
        s = raw.get("systemInfo") or {}
        service = raw.get("serviceInfo") or {}
        return FlightStatus(
            provider=self.id,
            airline=self.name,
            flight_number=f.get("flightNumberInfo") or s.get("flightNo") or "",
            origin=Airport(
                f.get("departureAirportCodeIata") or f["departureAirportCode"],
                f["departureAirportLatitude"],
                f["departureAirportLongitude"],
            ),
            destination=Airport(
                f.get("destinationAirportCodeIata") or f["destinationAirportCode"],
                f["destinationAirportLatitude"],
                f["destinationAirportLongitude"],
            ),
            time=parse_time(f["utcTime"]),
            latitude=f["latitude"],
            longitude=f["longitude"],
            altitude_ft=f["altitude"],
            ground_speed_mph=f["hspeed"],  # Gogo reports mph (checked against position changes)
            vertical_speed=f.get("vspeed") or 0.0,
            aircraft_type=s.get("aircraftType", ""),
            tail_number=f.get("tailNumber") or "",
            departure_time=parse_time(f.get("departureTime")),
            expected_arrival=parse_time(f.get("expectedArrival")),
            minutes_to_land=_int_or_none(s.get("timeToLand")),
            phase=(s.get("flightPhase") or "").replace("_", " ").title(),
            wifi=" · ".join(x for x in (s.get("linkState"), service.get("quality")) if x),
        )
