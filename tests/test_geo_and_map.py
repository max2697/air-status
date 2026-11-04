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
