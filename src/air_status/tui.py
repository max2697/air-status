"""Rich terminal UI: live status panel and history table."""

import time
from collections.abc import Sequence
from typing import Optional

from rich import box
from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from air_status.flight_map import FlightMap
from air_status.flightlog import FlightHistory
from air_status.geo import distance_km
from air_status.models import FlightStatus
from air_status.providers import Provider

WIDTH = 84
MAP_WIDTH = WIDTH - 8  # outer border + padding + map border
MIN_MAP_ROWS, MAX_MAP_ROWS = 6, 24
NON_MAP_ROWS = 14  # rows used by everything except the map
MPH_TO_KMH = 1.609
FT_TO_M = 0.3048


class Poller:
    """Fetches a reading every `every` seconds and saves it to the provider's history."""

    def __init__(self, provider: Provider, history: FlightHistory, every: int):
        self.provider, self.history, self.every = provider, history, every
        self.status: Optional[FlightStatus] = None
        self.track: list[FlightStatus] = []  # this flight's saved history, for the map
        self.fetched_at = 0.0
        self.error: Optional[str] = None

    def tick(self) -> None:
        if time.time() - self.fetched_at < self.every:
            return
        try:
            reading = self.provider.fetch()
            self.status, self.error = self.provider.parse(reading), None
        except Exception as e:  # network down, captive portal, format change… keep showing last data
            self.error = f"fetch failed: {e}"
        else:
            try:
                self.history.save(reading)
                self.track = self.history.track(reading)
            except (OSError, ValueError, KeyError) as e:
                self.error = f"history failed: {e}"
        self.fetched_at = time.time()


def progress(status: FlightStatus) -> float:
    """Share of the straight-line distance already covered, 0–100."""
    o, d = status.origin, status.destination
    total = distance_km(o.latitude, o.longitude, d.latitude, d.longitude)
    left = distance_km(status.latitude, status.longitude, d.latitude, d.longitude)
    return max(0.0, min(100.0, 100 * (1 - left / total))) if total else 0.0


def route_bar(pct: float, frm: str, to: str, width: int = 40) -> Align:
    pos = min(width - 1, int(width * pct / 100))
    line = Text()
    line.append(f" {frm} ", style="bold white on red")
    line.append("━" * pos, style="red")
    line.append("✈", style="bold yellow")
    line.append("┄" * (width - 1 - pos), style="grey50")
    line.append(f" {to} ", style="bold white on red")
    line.append(f"  {pct:.0f}%", style="bold")
    return Align.center(line)


def _local(dt) -> str:
    return f"{dt.astimezone():%H:%M} local" if dt else "—"


def _stats(st: FlightStatus) -> Table:
    vs = st.vertical_speed
    trend, color = ("▲ climbing", "green") if vs > 2 else ("▼ descending", "cyan") if vs < -2 else ("■ level", "grey62")
    left_km = distance_km(st.latitude, st.longitude, st.destination.latitude, st.destination.longitude)
    m = st.minutes_to_land
    eta = st.expected_arrival

    t = Table.grid(padding=(0, 3), expand=True)
    for style, justify in (("grey62", "right"), ("bold white", "left")) * 2:
        t.add_column(style=style, justify=justify)
    t.add_row(
        "Altitude",
        f"{st.altitude_ft:,.0f} ft  [{color}]{trend}[/]",
        "Speed",
        f"{st.ground_speed_mph:.0f} mph  [grey62]{st.ground_speed_mph * MPH_TO_KMH:,.0f} km/h[/]",
    )
    t.add_row("", f"[grey62]{st.altitude_ft * FT_TO_M:,.0f} m[/]", "Phase", f"[magenta]{st.phase or '—'}[/]")
    t.add_row("Remaining", f"{left_km:,.0f} km", "Position", f"{st.latitude:.3f}, {st.longitude:.3f}")
    t.add_row(
        "Time to land",
        f"[bold yellow]{m // 60}h {m % 60:02d}m[/]" if m is not None else "—",
        "ETA",
        f"{_local(eta)}  [grey62]{eta:%H:%M} UTC[/]" if eta else "—",
    )
    t.add_row("Departed", _local(st.departure_time), "Wi-Fi", st.wifi or "—")
    return t


def _footer(poller: Poller) -> Text:
    age = time.time() - poller.fetched_at
    nxt = max(0, poller.every - age)
    ok = poller.error is None
    footer = Text.assemble(
        ("● LIVE  " if ok else "● STALE  ", "bold green" if ok else "bold red"),
        (f"updated {age:.0f}s ago · next in {nxt:.0f}s · Ctrl+C to quit", "grey50"),
    )
    if not ok:
        footer.append(f"\n{poller.error}", style="red")
    return footer


def render(poller: Poller, flight_map: FlightMap, map_rows: int = 18) -> RenderableType:
    st = poller.status
    if st is None:
        return Text(poller.error or "Connecting…")
    parts: list[RenderableType] = [
        Text(),
        route_bar(progress(st), st.origin.code, st.destination.code),
        Text(),
        _stats(st),
        Text(),
    ]
    if map_rows >= MIN_MAP_ROWS:
        try:
            m = flight_map.render(st, MAP_WIDTH, map_rows, poller.track)
            parts.append(Panel(m, border_style="grey35", padding=0))
        except Exception as e:  # map is optional: missing data, no network for the download…
            parts.append(Text(f"map unavailable: {e}", style="grey50"))
    parts.append(Align.center(_footer(poller)))

    aircraft = " · ".join(x for x in (st.aircraft_type, st.tail_number) if x)
    title = Text.assemble(
        (f"✈ {st.airline} ", "bold red"), (st.flight_number, "bold white"), (f"   {aircraft}", "grey62")
    )
    return Panel(Group(*parts), title=title, border_style="red", padding=(0, 2), width=WIDTH)


def run_live(poller: Poller, flight_map: FlightMap) -> None:
    console = Console()
    if not console.is_terminal:
        # Not a real terminal (e.g. PyCharm Run window): print one frame per update.
        while True:
            poller.tick()
            console.print(render(poller, flight_map))
            time.sleep(poller.every)
    with Live(Text("Connecting…"), refresh_per_second=2, screen=True) as live:
        while True:
            poller.tick()
            rows = min(MAX_MAP_ROWS, console.size.height - NON_MAP_ROWS)
            live.update(render(poller, flight_map, rows))
            time.sleep(0.5)


def history_table(histories: Sequence[FlightHistory]) -> Optional[Table]:
    """Saved flights of all providers; each provider reads its own files."""
    t = Table(title="Saved flights", header_style="bold red", box=box.SIMPLE_HEAD)
    for col in ("Date", "Flight", "Route", "Type", "Pts", "UTC", "Max alt", "Size"):
        t.add_column(col, no_wrap=True)
    for history in histories:
        for path in history.files():
            rows = history.load(path)
            if not rows:
                continue
            a, b = rows[0], rows[-1]
            t.add_row(
                (a.departure_time or a.time).date().isoformat(),
                a.flight_number,
                f"{a.origin.code}→{a.destination.code}",
                a.aircraft_type,
                str(len(rows)),
                f"{a.time:%H:%M}–{b.time:%H:%M}",
                f"{max(r.altitude_ft for r in rows):,.0f}",
                f"{path.stat().st_size / 1024:,.0f}K",
            )
    return t if t.row_count else None
