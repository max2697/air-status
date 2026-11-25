import json
import ssl
from datetime import datetime, timezone
from io import BytesIO
from urllib.error import URLError

import pytest

from air_status.providers import PROVIDERS, get_provider
from air_status.providers import southwest as swa
from air_status.providers.aircanada import AirCanada
from air_status.tui import progress


def test_registry():
    assert isinstance(PROVIDERS["aircanada"], AirCanada)
    assert isinstance(get_provider("southwest"), swa.Southwest)
    with pytest.raises(ValueError):
        get_provider("nope")


def test_gogo_parse(status):
    assert status.provider == "aircanada"
    assert status.airline == "Air Canada"
    assert status.flight_number == "ACA123"
    assert (status.origin.code, status.destination.code) == ("AUS", "YYZ")
    assert status.time == datetime(2026, 1, 15, 18, 19, 58, tzinfo=timezone.utc)
    assert status.minutes_to_land == 165
    assert status.phase == "En Route"
    assert status.wifi == "UP · Good"
    assert status.aircraft_type == "A320"


def test_gogo_parse_tolerates_missing_extras(gogo_response):
    del gogo_response["systemInfo"], gogo_response["serviceInfo"]
    gogo_response["flightInfo"]["departureAirportCodeIata"] = None
    st = AirCanada().parse(gogo_response)
    assert st.origin.code == "KAUS"  # falls back to ICAO
    assert st.minutes_to_land is None and st.phase == "" and st.wifi == ""


# Trimmed real responses from aainflight.com with made-up flight values (Viasat)
AA_FLIGHT = {
    "timestamp": "2026-01-15T18:00:43Z",
    "eta": "20:00",
    "flightDuration": 180,
    "flightNumber": "AAL123",
    "latitude": 38.5,
    "longitude": -85.25,
    "vehicleId": "N123AA",
    "destination": "KMIA",
    "origin": "KORD",
    "flightId": "N123AA_SF_20260115170000",
    "altitude": 35000,
    "groundspeed": 450,
    "heading": 160,
    "timeToGo": 120,
    "flightPhase": "Cruise",
}
AA_GROUND_MIA = {
    "airport": {
        "locationDetails": {
            "basicAirportInformation": {"code": "MIA"},
            "airportCoordinates": {
                "airportLatitudeCoordinates": {
                    "geographicDegrees": 25,
                    "geographicMinute": 47,
                    "geographicSeconds": 43,
                    "latitudeHemiCode": "N",
                },
                "airportLongitudeCoordinates": {
                    "geographicDegrees": 80,
                    "geographicMinute": 17,
                    "geographicSeconds": 24,
                    "longitudeHemiCode": "W",
                },
            },
        }
    }
}


def aa_reading():
    from air_status.providers.american import airport_from_ground

    return {
        "flight": dict(AA_FLIGHT),
        "airports": {
            "KORD": {"iata": "ORD", "latitude": 41.97861, "longitude": -87.90472},
            "KMIA": airport_from_ground(AA_GROUND_MIA),
        },
        "satellite": {"state": "Available", "band": "Ka"},
    }


def test_icao_to_iata():
    from air_status.providers.american import icao_to_iata

    assert icao_to_iata("KDFW") == "DFW"
    assert icao_to_iata("CYYZ") == "YYZ"
    assert icao_to_iata("PHNL") == "HNL"
    assert icao_to_iata("EGLL") is None


def test_american_airport_from_ground():
    from air_status.providers.american import airport_from_ground

    a = airport_from_ground(AA_GROUND_MIA)
    assert a["iata"] == "MIA"
    assert a["latitude"] == pytest.approx(25.795, abs=1e-3)
    assert a["longitude"] == pytest.approx(-80.29, abs=1e-3)


def test_american_parse():
    st = get_provider("american").parse(aa_reading())
    assert st.airline == "American Airlines"
    assert st.flight_number == "AAL123"
    assert (st.origin.code, st.destination.code) == ("ORD", "MIA")
    assert st.time == datetime(2026, 1, 15, 18, 0, 43, tzinfo=timezone.utc)
    assert st.ground_speed_mph == pytest.approx(450 * 1.15078)
    assert st.minutes_to_land == 120
    assert st.expected_arrival == datetime(2026, 1, 15, 20, 0, 43, tzinfo=timezone.utc)
    assert st.departure_time == datetime(2026, 1, 15, 17, 0, 43, tzinfo=timezone.utc)
    assert st.tail_number == "N123AA"
    assert st.heading == 160
    assert st.phase == "Cruise"
    assert st.wifi == "Available · Ka"


def test_american_history_roundtrip(tmp_path):
    provider = get_provider("american")
    history = provider.history(tmp_path)
    first = aa_reading()
    later = aa_reading()
    later["flight"].update(timestamp="2026-01-16T00:10:00Z", latitude=30.0, timeToGo=10)
    assert history.save(first) and history.save(later)
    assert not history.save(later)
    (path,) = history.files()
    assert path.name == "2026-01-15_AAL123_ORD-MIA.jsonl"  # stays on departure day past midnight
    statuses = history.load(path)
    assert [s.latitude for s in statuses] == [38.5, 30.0]
    assert statuses[1].destination.code == "MIA"


class FakeProvider:
    def __init__(self, name, found, delay=0.0):
        self.name, self.found, self.delay = name, found, delay

    def detect(self):
        import time

        time.sleep(self.delay)
        return self.found


def test_detect_provider_picks_reachable_one():
    from air_status.providers import detect_provider

    hit = FakeProvider("b", True)
    assert detect_provider([FakeProvider("a", False), hit]) is hit
    assert detect_provider([FakeProvider("a", False)]) is None
    assert detect_provider([]) is None


def test_detect_provider_does_not_wait_for_slow_portals():
    import time

    from air_status.providers import detect_provider

    hit = FakeProvider("fast", True)
    start = time.monotonic()
    assert detect_provider([FakeProvider("slow", False, delay=2), hit]) is hit
    assert time.monotonic() - start < 1


def test_gogo_detect_checks_airline(monkeypatch, gogo_response):
    ac = AirCanada()
    monkeypatch.setattr(ac, "fetch", lambda: gogo_response)
    assert ac.detect()
    gogo_response["flightInfo"]["airlineCode"] = "DAL"
    assert not ac.detect()


def test_detect_false_when_unreachable(monkeypatch):
    aa = get_provider("american")

    def boom():
        raise OSError("no route")

    monkeypatch.setattr(aa, "fetch", boom)
    assert not aa.detect()


def test_american_vertical_speed_from_altitude():
    from air_status.providers.american import American

    aa = American()

    def at(second, altitude, flight_id="N123AA_SF_20260115170000"):
        flight = dict(AA_FLIGHT, altitude=altitude, flightId=flight_id)
        flight["timestamp"] = f"2026-01-15T18:{second // 60:02d}:{second % 60:02d}Z"
        return aa._vertical_speed(flight)

    assert at(0, 20000) is None  # need at least CLIMB_MIN_SPAN seconds
    assert at(6, 20200) is None
    assert at(6, 20200) is None  # repeated reading is ignored
    assert at(20, 20600) == 30.0  # 600 ft in 20 s
    assert at(80, 22100) == 25.0  # window keeps the last 60 s: 20600 -> 22100
    assert at(86, 30000, flight_id="other") is None  # new flight starts over

    jitter = American()
    for second, alt in ((0, 35000), (6, 35010), (12, 34995), (18, 35008)):
        flight = dict(AA_FLIGHT, altitude=alt, timestamp=f"2026-01-15T18:00:{second:02d}Z")
        vs = jitter._vertical_speed(flight)
    assert abs(vs) < 2  # cruise jitter stays "level"


def test_american_parse_uses_climb():
    reading = aa_reading()
    assert get_provider("american").parse(reading).vertical_speed == 0.0
    reading["climb"] = {"verticalSpeed": -25.0}
    assert get_provider("american").parse(reading).vertical_speed == -25.0


def test_southwest_fetch_and_history(monkeypatch, tmp_path):
    requests = []
    tracker = {
        "flight_number": "9876",
        "operating_carrier": "WN",
        "departure_airport_code": "DAL",
        "arrival_airport_code": "DEN",
        "departure_utc_at": "2035-05-04T23:15:00Z",
        "current_utc_at": "2035-05-05T00:15:00Z",
        "arrival_utc_at": "2035-05-05T01:15:00Z",
    }
    stations = [
        {"id": "DAL", "latitude": "32.847", "longitude": "-96.852"},
        {"id": "DEN", "latitude": "39.856", "longitude": "-104.673"},
    ]
    responses = {
        swa.CLIENT_CONTEXT: json.dumps({"clientId": "test-client", "routerId": "test-router", "sandboxId": 1}),
        f"{swa.PORTAL}/": '<script src="/inflight/home-page/static/1.2.3/js/app.js"></script>',
        swa.BOOTSTRAP: (
            '"/api-keys":[function(require,module,exports){\nmodule.exports = {"prod":"test-key"};\n'
            f'"/air/all-air-stations":[function(require,module,exports){{\nmodule.exports = {json.dumps(stations)};'
        ),
        f"{swa.API}/flight-data": json.dumps({"tail_number": "N987T"}),
        f"{swa.API}/flight-tracker-data?tail_number=N987T": json.dumps({"data": tracker}),
    }

    def read(url, headers=None, body=None):
        requests.append((url, headers, body))
        return responses[url].encode()

    monkeypatch.setattr(swa, "_read", read)
    provider = swa.Southwest()
    reading = provider.fetch()
    assert provider.detect()
    assert requests[3][2] == {"client_id": "test-client", "router_id": "test-router", "sandbox_id": 1}
    assert requests[4][1]["X-Api-Key"] == "test-key"
    assert reading == {
        "tail_number": "N987T",
        **tracker,
        "airport_coordinates": {"DAL": [32.847, -96.852], "DEN": [39.856, -104.673]},
    }

    status = provider.parse(reading)
    assert status.provider == "southwest"
    assert status.flight_number == "WN9876"
    assert (status.origin.code, status.destination.code) == ("DAL", "DEN")
    assert status.origin.coordinates == (32.847, -96.852)
    assert status.destination.coordinates == (39.856, -104.673)
    assert status.position is status.altitude_ft is status.ground_speed_mph is None
    assert status.expected_arrival == datetime(2035, 5, 5, 1, 15, tzinfo=timezone.utc)
    assert status.minutes_to_land == 60
    assert progress(status) == 50

    history = provider.history(tmp_path)
    assert history.save(reading)
    assert not provider.history(tmp_path).save(reading)
    (path,) = history.files()
    assert path.name == "2035-05-04_WN9876_DAL-DEN.jsonl"
    assert history.load(path) == [status]

    old_reading = {"tail_number": "N987T", **tracker}
    assert provider.parse(old_reading).origin.coordinates is None
    assert progress(provider.parse(old_reading)) == 50


def test_southwest_detect_requires_a_current_flight(monkeypatch):
    provider = swa.Southwest()
    monkeypatch.setattr(provider, "fetch", lambda: dict.fromkeys(swa.TRACKER_FIELDS))
    assert not provider.detect()


@pytest.mark.parametrize(
    ("url", "verify_code", "retry"),
    [(swa.CLIENT_CONTEXT, 20, True), (swa.CLIENT_CONTEXT, 62, False), (swa.PORTAL, 20, False)],
)
def test_southwest_downloads_intermediate_only_for_missing_router_issuer(monkeypatch, url, verify_code, retry):
    error = ssl.SSLCertVerificationError()
    error.verify_code = verify_code
    fallback = object()
    calls = []

    def open_url(request, *, timeout, context=None):
        calls.append(context)
        if context is None:
            raise URLError(error)
        return BytesIO(b"{}")

    monkeypatch.setattr(swa.urllib.request, "urlopen", open_url)
    monkeypatch.setattr(swa, "_starlink_tls", lambda: fallback)
    if retry:
        assert swa._read(url) == b"{}"
        assert calls == [None, fallback]
    else:
        with pytest.raises(URLError):
            swa._read(url)
        assert calls == [None]
