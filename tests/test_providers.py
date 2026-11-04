from datetime import datetime, timezone

import pytest

from air_status.providers import PROVIDERS, get_provider
from air_status.providers.aircanada import AirCanada


def test_registry():
    assert isinstance(PROVIDERS["aircanada"], AirCanada)
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
