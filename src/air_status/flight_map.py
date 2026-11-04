"""Terminal map of a flight: Natural Earth outlines, route and plane on a Braille canvas."""

import json
import math
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.text import Text

from air_status.braille import Canvas
from air_status.geo import LatLon, distance_km, great_circle
from air_status.models import FlightStatus

SOURCE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/{}.geojson"
# (dataset, style, priority) — a higher priority wins the colour of a shared cell
LAYERS = (
    ("ne_50m_admin_1_states_provinces_lines", "grey27", 1),
    ("ne_50m_admin_0_boundary_lines_land", "grey58", 2),
    ("ne_50m_lakes", "dodger_blue3", 3),
    ("ne_50m_coastline", "dodger_blue3", 3),
)
MAX_LAKE_RANK = 2  # only big lakes; small ones are noise at this scale

Path_ = list[list[float]]


def _paths(coords) -> list[Path_]:
    """Every [[lon, lat], ...] list inside any GeoJSON geometry."""
    if coords and isinstance(coords[0][0], (int, float)):
        return [coords]
    return [p for c in coords for p in _paths(c)]


def load_layers(map_dir: Path) -> list[tuple[list[Path_], str, int]]:
    """Load outlines, downloading each dataset once into map_dir."""
    map_dir.mkdir(parents=True, exist_ok=True)
    layers = []
    for name, style, prio in LAYERS:
        path = map_dir / f"{name}.geojson"
        if not path.exists():
            urllib.request.urlretrieve(SOURCE_URL.format(name), path)
        features = json.loads(path.read_text())["features"]
        if name == "ne_50m_lakes":
            features = [f for f in features if f["properties"].get("scalerank", 9) <= MAX_LAKE_RANK]
        layers.append(([p for f in features for p in _paths(f["geometry"]["coordinates"])], style, prio))
    return layers


MAX_RECORDED_GAP = 60  # seconds; longer gaps between saved points are drawn as estimated


@dataclass
class Leg:
    """Part of the flown path: `recorded` legs come from history, the rest are estimated."""

    points: list[LatLon]
    recorded: bool


def geoline(a: LatLon, b: LatLon, step_km: float = 20) -> list[LatLon]:
    """Shortest path on the globe from a to b, one point per `step_km`."""
    n = max(1, int(distance_km(*a, *b) / step_km))
    return great_circle(*a, *b, n=n)


def flown_legs(status: FlightStatus, track: Sequence[FlightStatus] = ()) -> list[Leg]:
    """Path from the origin to the current position.

    Consecutive saved points less than MAX_RECORDED_GAP apart are joined as recorded;
    everything else (origin → first point, gaps, no history at all) is a geoline
    between the two known points, marked as estimated.
    """
    known: list[tuple[LatLon, Optional[datetime]]] = [((status.origin.latitude, status.origin.longitude), None)]
    known += [((t.latitude, t.longitude), t.time) for t in track if t.time <= status.time]
    if known[-1][1] != status.time:
        known.append(((status.latitude, status.longitude), status.time))

    legs: list[Leg] = []
    for (a, ta), (b, tb) in zip(known, known[1:]):
        recorded = ta is not None and tb is not None and (tb - ta).total_seconds() <= MAX_RECORDED_GAP
        if recorded and legs and legs[-1].recorded:
            legs[-1].points.append(b)  # extend the current recorded run
        elif recorded:
            legs.append(Leg([a, b], True))
        else:
            legs.append(Leg(geoline(a, b), False))
    return legs


class FlightMap:
    """Draws the base map once per route and size, then overlays route and plane each frame."""

    def __init__(self, map_dir: Path):
        self.map_dir = map_dir
        self._layers: Optional[list] = None
        self._key: Optional[tuple] = None
        self._base: Optional[Canvas] = None
        self._route_key: Optional[tuple] = None
        self._route: Optional[Canvas] = None

    def _setup(self, status: FlightStatus, width: int, height: int) -> None:
        if self._layers is None:
            self._layers = load_layers(self.map_dir)
        o, d = status.origin, status.destination
        route = great_circle(o.latitude, o.longitude, d.latitude, d.longitude)
        lats = [p[0] for p in route]
        lons = [p[1] for p in route]
        mid_lat = (max(lats) + min(lats)) / 2
        mid_lon = (max(lons) + min(lons)) / 2
        kx = math.cos(math.radians(mid_lat))  # squash longitude so shapes look right
        pw, ph = width * 2, height * 4
        span_x = (max(lons) - min(lons)) * kx * 1.3 + 1
        span_y = (max(lats) - min(lats)) * 1.3 + 1
        scale = min(pw / span_x, ph / span_y)

        def project(lat: float, lon: float) -> tuple[float, float]:
            return pw / 2 + (lon - mid_lon) * kx * scale, ph / 2 - (lat - mid_lat) * scale

        self._project = project
        base = Canvas(width, height)
        for paths, style, prio in self._layers:
            for path in paths:
                pts = [project(lat, lon) for lon, lat, *_ in path]
                for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                    base.line(x0, y0, x1, y1, style, prio)
        self._base = base

    def _draw_route(self, status: FlightStatus, track: Sequence[FlightStatus], width: int, height: int) -> Canvas:
        project = self._project
        here = (status.latitude, status.longitude)
        dst = (status.destination.latitude, status.destination.longitude)
        route = Canvas(width, height)

        ahead = [project(*p) for p in geoline(here, dst)]
        for i, ((x0, y0), (x1, y1)) in enumerate(zip(ahead, ahead[1:])):
            if i % 2 == 0:  # dashed remaining leg
                route.line(x0, y0, x1, y1, "bright_white", 8)

        for leg in flown_legs(status, track):
            pts = [project(*p) for p in leg.points]
            for i, ((x0, y0), (x1, y1)) in enumerate(zip(pts, pts[1:])):
                if leg.recorded:
                    route.line(x0, y0, x1, y1, "bold red", 10)
                elif i % 2 == 0:  # dashed: estimated, not from history
                    route.line(x0, y0, x1, y1, "red3", 9)
        return route

    def render(self, status: FlightStatus, width: int, height: int, track: Sequence[FlightStatus] = ()) -> Text:
        """Map for one status, `width` x `height` terminal cells.

        `track` is this flight's saved history; without it the flown path is estimated.
        """
        dep_code, dst_code = status.origin.code, status.destination.code
        key = (dep_code, dst_code, width, height)
        if key != self._key:
            self._setup(status, width, height)
            self._key = key
        route_key = (key, status.time, len(track))
        if route_key != self._route_key:  # redraw the route only when data changes
            self._route = self._draw_route(status, track, width, height)
            self._route_key = route_key
        canvas = self._base.copy()
        canvas.overlay(self._route)  # route stays crisp over borders
        project = self._project
        here = (status.latitude, status.longitude)
        dep = (status.origin.latitude, status.origin.longitude)
        dst = (status.destination.latitude, status.destination.longitude)

        for code, (lat, lon) in ((dep_code, dep), (dst_code, dst)):
            x, y = project(lat, lon)
            cx, cy = int(x) // 2, int(y) // 4
            canvas.text(cx, cy, "●", "bold white")
            label = f" {code} "
            lx = cx + 2 if cx + 2 + len(label) <= width else cx - 1 - len(label)
            canvas.text(lx, cy, label, "bold white on red")

        x, y = project(*here)
        canvas.text(int(x) // 2, int(y) // 4, "✈", "bold yellow")
        return canvas.to_text()
