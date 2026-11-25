import dataclasses
from datetime import timedelta
from io import StringIO

import pytest
from rich.console import Console

from air_status.flight_map import FlightMap, flown_legs
from air_status.geo import distance_km
from air_status.tui import Poller, render


def _at(status, seconds, lat, lon):
    return dataclasses.replace(status, time=status.time + timedelta(seconds=seconds), latitude=lat, longitude=lon)


def test_no_history_is_one_estimated_geoline(status):
    legs = flown_legs(status)
    assert len(legs) == 1 and not legs[0].recorded
    assert legs[0].points[0] == pytest.approx((status.origin.latitude, status.origin.longitude))
    assert legs[0].points[-1] == pytest.approx((status.latitude, status.longitude))


def test_history_is_recorded_after_estimated_start(status):
    track = [_at(status, 0, 31.0, -97.0), _at(status, 10, 31.1, -96.9), _at(status, 20, 31.2, -96.8)]
    legs = flown_legs(track[-1], track)
    assert [leg.recorded for leg in legs] == [False, True]  # origin → first point, then the saved track
    assert legs[1].points == [(31.0, -97.0), (31.1, -96.9), (31.2, -96.8)]


def test_gap_in_history_is_estimated(status):
    track = [_at(status, 0, 31.0, -97.0), _at(status, 10, 31.1, -96.9), _at(status, 300, 32.0, -96.0)]
    legs = flown_legs(track[-1], track)
    assert [leg.recorded for leg in legs] == [False, True, False]


def test_current_position_newer_than_history_is_appended(status):
    track = [_at(status, 0, 31.0, -97.0)]
    now = _at(status, 10, 31.1, -96.9)
    legs = flown_legs(now, track)
    assert legs[-1].recorded and legs[-1].points[-1] == (31.1, -96.9)


def test_map_estimates_position_from_progress(status, tmp_path, monkeypatch):
    status = dataclasses.replace(
        status,
        latitude=None,
        longitude=None,
        altitude_ft=None,
        ground_speed_mph=None,
        departure_time=status.time - timedelta(hours=1),
        expected_arrival=status.time + timedelta(hours=1),
        minutes_to_land=60,
        phase="",
        wifi="Starlink",
    )
    flight_map = FlightMap(tmp_path)
    monkeypatch.setattr("air_status.flight_map.load_layers", lambda _: [])
    draw_route = flight_map._draw_route
    positions = []

    def capture(placed_status, track, width, height):
        assert not track
        positions.append(placed_status.position)
        return draw_route(placed_status, track, width, height)

    monkeypatch.setattr(flight_map, "_draw_route", capture)
    poller = Poller(None, None, 60)
    poller.track = [status]
    poller.status = status
    output = StringIO()
    Console(file=output, width=100).print(render(poller, flight_map))
    frame = output.getvalue()
    for label in ("Estimated position · elapsed flight time", "Time to land", "ETA", "Departed", "Starlink"):
        assert label in frame
    for label in ("Altitude", "Speed", "Phase", "Remaining", "Position", "—"):
        assert label not in frame

    # A revised ETA can move the estimate even when the source timestamp is unchanged.
    later_eta = dataclasses.replace(status, expected_arrival=status.expected_arrival + timedelta(hours=2))
    flight_map.render(later_eta, 76, 18)
    origin, destination = status.origin.coordinates, status.destination.coordinates
    total = distance_km(*origin, *destination)
    assert distance_km(*origin, *positions[0]) == pytest.approx(total * 0.5)
    assert distance_km(*origin, *positions[1]) == pytest.approx(total * 0.25)
    assert status.position is None
