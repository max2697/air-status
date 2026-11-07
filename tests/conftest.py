import copy

import pytest

# Gogo / Intelsat statusTray response shape, with made-up flight values
GOGO_RESPONSE = {
    "status": 200,
    "flightInfo": {
        "airlineCode": "ACA",
        "tailNumber": "CABCD",
        "flightNumberInfo": "ACA123",
        "departureAirportCode": "KAUS",
        "destinationAirportCode": "CYYZ",
        "departureAirportCodeIata": "AUS",
        "destinationAirportCodeIata": "YYZ",
        "departureAirportLatitude": 30.29,
        "departureAirportLongitude": -97.7,
        "destinationAirportLatitude": 43.67,
        "destinationAirportLongitude": -79.62,
        "expectedArrival": "2026-01-15T21:03:00.00Z",
        "departureTime": "2026-01-15T18:04:55.00Z",
        "latitude": 31.5848,
        "longitude": -97.8442,
        "altitude": 22650.834,
        "utcTime": "2026-01-15T18:19:58.627Z",
        "hspeed": 549.20905,
        "vspeed": 13.909091,
    },
    "gogoFacts": "trivia",
    "serviceInfo": {"service": "Active", "quality": "Good", "alerts": []},
    "ipAddress": "10.0.0.2",
    "macAddress": "02:00:00:00:00:01",
    "systemInfo": {"flightPhase": "EN_ROUTE", "timeToLand": "165", "linkState": "UP", "aircraftType": "A320"},
    "device_iid": "abc",
}


@pytest.fixture
def gogo_response():
    return copy.deepcopy(GOGO_RESPONSE)


@pytest.fixture
def status(gogo_response):
    from air_status.providers.aircanada import AirCanada

    return AirCanada().parse(gogo_response)
