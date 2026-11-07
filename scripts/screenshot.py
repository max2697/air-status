"""Make the README screenshot from a made-up flight (no real flight data, see CLAUDE.md).

    .venv/bin/python scripts/screenshot.py            # writes docs/screenshot.png

Rich draws the frame as SVG; Google Chrome (headless) turns it into the PNG.
"""

import io
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console

from air_status.flight_map import FlightMap
from air_status.geo import great_circle
from air_status.models import Airport, FlightStatus
from air_status.tui import WIDTH, Poller, render

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

ORIGIN = Airport("ORD", 41.97861, -87.90472)
DESTINATION = Airport("MIA", 25.79528, -80.29)
DEPARTED = datetime(2026, 1, 15, 17, 0, tzinfo=timezone.utc)
FLIGHT_MINUTES = 180
PROGRESS = 0.55  # share of the route flown


def made_up_flight() -> tuple[FlightStatus, list[FlightStatus]]:
    route = great_circle(ORIGIN.latitude, ORIGIN.longitude, DESTINATION.latitude, DESTINATION.longitude, n=400)
    flown = route[: int(len(route) * PROGRESS)]
    start = 20  # recording started a little after takeoff
    track = []
    for i, (lat, lon) in enumerate(flown[start:], start):
        t = DEPARTED + timedelta(minutes=FLIGHT_MINUTES * i / len(route))
        track.append(
            FlightStatus(
                provider="american",
                airline="American Airlines",
                flight_number="AAL123",
                origin=ORIGIN,
                destination=DESTINATION,
                time=t,
                latitude=lat,
                longitude=lon,
                altitude_ft=min(36000, 12000 + 600 * (i - start)),
                ground_speed_mph=512,
                tail_number="N123AA",
                heading=160,
                departure_time=DEPARTED,
                expected_arrival=DEPARTED + timedelta(minutes=FLIGHT_MINUTES),
                phase="Cruise",
                wifi="Available · Ka",
            )
        )
    status = track[-1]
    status.minutes_to_land = round((status.expected_arrival - status.time).total_seconds() / 60)
    return status, track


def main() -> None:
    os.environ["TZ"] = "America/Chicago"  # stable "local" times in the picture
    time.tzset()
    status, track = made_up_flight()
    poller = Poller(provider=None, history=None, every=6)
    poller.status, poller.track, poller.fetched_at = status, track, time.time() - 1

    console = Console(record=True, width=WIDTH, file=io.StringIO(), force_terminal=True, color_system="truecolor")
    console.print(render(poller, FlightMap(ROOT / "mapdata"), map_rows=20))
    if not Path(CHROME).exists():
        sys.exit("needs Google Chrome to turn the SVG into a PNG")
    OUT.mkdir(exist_ok=True)
    svg_path = Path(tempfile.mkdtemp()) / "screenshot.svg"
    console.save_svg(str(svg_path), title="air-status")

    # Chrome falls back to "Apple Braille Outline" for bold map cells (hollow dots); pin the plain font
    svg = svg_path.read_text()
    braille_face = (
        '@font-face { font-family: "Map Braille"; src: local("Apple Braille"), local("DejaVu Sans Mono");'
        " unicode-range: U+2800-28FF; font-weight: 100 900; }\n"
    )
    svg = svg.replace("<style>", "<style>\n" + braille_face, 1)
    svg = svg.replace("font-family: Fira Code, monospace;", 'font-family: "Map Braille", Fira Code, monospace;')
    svg_path.write_text(svg)

    w, h = (float(v) for v in re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg).groups())
    png_path = OUT / "screenshot.png"
    subprocess.run(
        [
            CHROME,
            "--headless",
            "--hide-scrollbars",
            "--force-device-scale-factor=2",
            "--default-background-color=00000000",
            f"--window-size={int(w)},{int(h)}",
            f"--screenshot={png_path}",
            svg_path.as_uri(),
        ],
        check=True,
        capture_output=True,
    )
    print(f"wrote {png_path}")


if __name__ == "__main__":
    main()
