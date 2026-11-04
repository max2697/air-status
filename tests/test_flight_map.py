import dataclasses
from datetime import timedelta

import pytest

from air_status.flight_map import flown_legs


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
