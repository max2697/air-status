"""Southwest Airlines' Starlink passenger flight tracker."""

import base64
import json
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from functools import cached_property, lru_cache
from hashlib import sha256
from math import ceil
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from uuid import uuid4

from asn1crypto.cms import ContentInfo

from air_status.flightlog import ChangeLog, safe_part
from air_status.models import Airport, FlightStatus
from air_status.providers.base import Provider

Raw = dict[str, Any]

PORTAL = "https://southwestwifi.com"
BOOTSTRAP = f"{PORTAL}/swa-ui/bootstrap/inflight-home-page/1/data.js"
CLIENT_CONTEXT = "https://starlink.southwestwifi.com/starlinkrouter/sandbox-client"
API = f"{PORTAL}/api/inflight-portal/v1/inflight-portal"
INTERMEDIATE_BUNDLE = "https://www.identrust.com/sites/default/files/resources/HydrantID%20Server%20CA%2001.p7b"
INTERMEDIATE_SHA256 = "8bb2f6883fed289a521ba27c478482950874e143caccec6fc025990c0c46813e"
MISSING_ISSUER_CODES = (20, 21)
APP_VERSION = re.compile(r"/inflight/home-page/static/([\d.]+)/js/app\.js")
API_KEYS = re.compile(r'/api-keys":\[function[^\n]*\s+module\.exports\s*=\s*(\{[^\n]+\})')
AIR_STATIONS = re.compile(r'/air/all-air-stations":\[function[^\n]*\s+module\.exports\s*=\s*(\[[^\n]+\]);')
TRACKER_FIELDS = (
    "flight_number",
    "operating_carrier",
    "departure_airport_code",
    "arrival_airport_code",
    "current_utc_at",
    "departure_utc_at",
    "arrival_utc_at",
)


@lru_cache(maxsize=1)
def _starlink_tls() -> ssl.SSLContext:
    # IdenTrust publishes a base64-encoded PKCS#7 bundle containing the intermediate and root.
    with urllib.request.urlopen(INTERMEDIATE_BUNDLE, timeout=8) as response:
        bundle = base64.b64decode(b"".join(response.read(16384).split()), validate=True)
    choices = ContentInfo.load(bundle, strict=True)["content"]["certificates"]
    certificates = (choice.chosen.dump() for choice in choices if choice.name == "certificate")
    intermediate = next((cert for cert in certificates if sha256(cert).hexdigest() == INTERMEDIATE_SHA256), None)
    if intermediate is None:
        raise ValueError("IdenTrust bundle lacks the expected Southwest intermediate")

    # Load only the intermediate and require a root from the system trust store.
    context = ssl.create_default_context()
    context.verify_flags &= ~getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(intermediate))
    return context


def _read(url: str, headers: Optional[dict[str, str]] = None, body: Optional[Raw] = None) -> bytes:
    headers = dict(headers or {})
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=8)
    except urllib.error.URLError as error:
        reason = error.reason
        if (
            url != CLIENT_CONTEXT
            or not isinstance(reason, ssl.SSLCertVerificationError)
            or reason.verify_code not in MISSING_ISSUER_CODES
        ):
            raise
        response = urllib.request.urlopen(request, timeout=8, context=_starlink_tls())
    with response:
        return response.read()


def _utc_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    time = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return time.replace(tzinfo=timezone.utc) if time.tzinfo is None else time.astimezone(timezone.utc)


class SouthwestHistory(ChangeLog):
    def path_for(self, reading: Raw) -> Path:
        status = Southwest.parse(reading)
        day = (status.departure_time or status.time).date().isoformat()
        route = f"{safe_part(status.origin.code)}-{safe_part(status.destination.code)}"
        return self.flight_file(day, status.flight_number, route)

    def to_record(self, reading: Raw) -> Raw:
        return reading  # fetch() only returns flight fields

    def from_record(self, record: Raw) -> FlightStatus:
        return Southwest.parse(record)


class Southwest(Provider):
    id = "southwest"
    name = "Southwest Airlines"
    update_interval = 60  # the passenger portal polls the tracker once per minute

    @cached_property
    def _bootstrap(self) -> str:
        return _read(BOOTSTRAP).decode()

    @cached_property
    def _headers(self) -> dict[str, str]:
        version = APP_VERSION.search(_read(f"{PORTAL}/").decode())
        keys = API_KEYS.search(self._bootstrap)
        if not version or not keys:
            raise ValueError("Southwest portal client configuration unavailable")
        version = version[1]
        return {
            "Accept": "application/json",
            "Origin": PORTAL,
            "Referer": f"{PORTAL}/",
            "X-Api-Key": json.loads(keys[1])["prod"],
            "X-App-Id": "inflight-home-page",
            "X-App-Version": version,
            "X-Channel-Id": "southwest",
            "X-Diagnostic": json.dumps({"spa": version}),
            "X-User-Experience-Id": str(uuid4()),
        }

    @cached_property
    def _airports(self) -> dict[str, list[float]]:
        stations = AIR_STATIONS.search(self._bootstrap)
        if not stations:
            return {}
        try:
            station_data = json.loads(stations[1])
        except json.JSONDecodeError:
            return {}
        airports = {}
        for station in station_data:
            try:
                code = station["id"]
                latitude, longitude = float(station["latitude"]), float(station["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                airports[code] = [latitude, longitude]
        return airports

    def fetch(self) -> Raw:
        context = json.loads(_read(CLIENT_CONTEXT))
        if not (context.get("clientId") and context.get("routerId") and context.get("sandboxId")):
            raise ValueError("Southwest Starlink network unavailable")
        flight = json.loads(
            _read(
                f"{API}/flight-data",
                self._headers,
                {
                    "client_id": context["clientId"],
                    "router_id": context["routerId"],
                    "sandbox_id": context["sandboxId"],
                },
            )
        )
        tail = flight.get("tail_number")
        if not tail:
            raise ValueError("Southwest portal did not identify the aircraft")
        query = urlencode({"tail_number": tail})
        tracker = json.loads(_read(f"{API}/flight-tracker-data?{query}", self._headers))["data"]
        codes = (tracker.get("departure_airport_code"), tracker.get("arrival_airport_code"))
        return {
            "tail_number": tail,
            **{key: tracker.get(key) for key in TRACKER_FIELDS},
            "airport_coordinates": {code: self._airports.get(code) for code in codes if code},
        }

    def history(self, directory: Path) -> SouthwestHistory:
        return SouthwestHistory(directory)

    @staticmethod
    def parse(reading: Raw) -> FlightStatus:
        time = _utc_time(reading["current_utc_at"])
        origin = reading["departure_airport_code"]
        destination = reading["arrival_airport_code"]
        number = reading["flight_number"]
        if time is None or not (origin and destination and number):
            raise ValueError("Southwest tracker has no current flight")
        arrival = _utc_time(reading["arrival_utc_at"])
        coordinates = reading.get("airport_coordinates", {})
        return FlightStatus(
            provider=Southwest.id,
            airline=Southwest.name,
            flight_number=f"{reading['operating_carrier'] or ''}{number}",
            origin=Airport(origin, *(coordinates.get(origin) or ())),
            destination=Airport(destination, *(coordinates.get(destination) or ())),
            time=time,
            latitude=None,
            longitude=None,
            altitude_ft=None,
            ground_speed_mph=None,
            tail_number=reading["tail_number"],
            departure_time=_utc_time(reading["departure_utc_at"]),
            expected_arrival=arrival,
            minutes_to_land=max(0, ceil((arrival - time).total_seconds() / 60)) if arrival else None,
            wifi="Starlink",
        )
