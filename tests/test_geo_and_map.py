import pytest

from air_status.braille import Canvas
from air_status.geo import distance_km, great_circle


def test_distance_aus_yyz():
    assert distance_km(30.29, -97.7, 43.67, -79.62) == pytest.approx(2180, abs=10)


def test_great_circle_endpoints():
    pts = great_circle(30.29, -97.7, 43.67, -79.62, n=10)
    assert len(pts) == 11
    assert pts[0] == pytest.approx((30.29, -97.7))
    assert pts[-1] == pytest.approx((43.67, -79.62))


def test_canvas_dots_and_text():
    c = Canvas(2, 1)
    c.dot(0, 0, "red")
    c.dot(1, 3, "red")
    c.text(1, 0, "✈", None)
    assert c.to_text().plain == chr(0x2800 | 0x01 | 0x80) + "✈"


def test_canvas_ignores_off_screen():
    c = Canvas(1, 1)
    c.line(-50, -50, -10, -10, "red")
    c.dot(5, 5, "red")
    assert c.to_text().plain == chr(0x2800)


def test_bearing_deg():
    from air_status.geo import bearing_deg

    assert bearing_deg(0, 0, 1, 0) == pytest.approx(0)
    assert bearing_deg(0, 0, 0, 1) == pytest.approx(90)
    assert bearing_deg(0, 0, -1, 0) == pytest.approx(180)
    assert bearing_deg(0, 0, 0, -1) == pytest.approx(270)


def test_plane_glyph():
    from air_status.flight_map import plane_glyph

    assert plane_glyph(0, -1) == "↑"
    assert plane_glyph(1, 0) == "→"
    assert plane_glyph(-1, 1) == "↙"
    assert plane_glyph(-1, -1) == "↖"
    assert plane_glyph(0, 0) == "✈"


def test_heading_of(status):
    from dataclasses import replace

    from air_status.flight_map import heading_of

    assert heading_of(replace(status, heading=247.0)) == 247.0
    assert 0 < heading_of(status) < 90  # no heading reported: towards destination (north-east)
