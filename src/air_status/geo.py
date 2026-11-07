"""Small spherical-earth helpers."""

import math

EARTH_RADIUS_KM = 6371

LatLon = tuple[float, float]


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    p = math.radians
    a = math.sin(p(lat2 - lat1) / 2) ** 2 + math.cos(p(lat1)) * math.cos(p(lat2)) * math.sin(p(lon2 - lon1) / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial direction from point 1 to point 2, degrees clockwise from north (0–360)."""
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360


def great_circle(lat1: float, lon1: float, lat2: float, lon2: float, n: int = 200) -> list[LatLon]:
    """n+1 evenly spaced (lat, lon) points along the shortest path between two places."""
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = [math.cos(p1) * math.cos(l1), math.cos(p1) * math.sin(l1), math.sin(p1)]
    b = [math.cos(p2) * math.cos(l2), math.cos(p2) * math.sin(l2), math.sin(p2)]
    d = math.acos(max(-1.0, min(1.0, sum(i * j for i, j in zip(a, b)))))
    points = []
    for step in range(n + 1):
        t = step / n
        if d < 1e-9:
            v = a
        else:
            k1, k2 = math.sin((1 - t) * d) / math.sin(d), math.sin(t * d) / math.sin(d)
            v = [k1 * i + k2 * j for i, j in zip(a, b)]
        points.append((math.degrees(math.atan2(v[2], math.hypot(v[0], v[1]))), math.degrees(math.atan2(v[1], v[0]))))
    return points
