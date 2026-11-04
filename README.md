# air-status

Live flight status in the terminal while you're on board, read from the airline's
in-flight Wi-Fi portal: altitude, speed, ETA, a Braille map of the route, and a
saved history of every flight.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Use

```bash
.venv/bin/air-status                     # live view (Air Canada), saves history
.venv/bin/air-status live -p aircanada --every 10
.venv/bin/air-status history             # list saved flights
```

Run it in a real terminal for the live full-screen view. In a plain output window
(e.g. PyCharm's Run tab) it prints one frame per update instead.

Files go in the current folder (change with `--data-dir`):

- `history/<provider>/` — one file per flight, in that provider's own format.
  Air Canada (Gogo) stores the raw portal data as change-only JSON Lines: the
  first line is the full reading, later lines hold only the fields that changed.
  Your device's IP/MAC address is never saved.
- `mapdata/` — map outlines from [Natural Earth](https://www.naturalearthdata.com/),
  downloaded on first run.

The map draws the flown path from history (solid red). Where there is no history,
such as before recording started or during gaps over 60 s, it draws an estimated
shortest-path line between the known points (dashed red).

## Adding an airline

Providers live in `src/air_status/providers/`. A provider:

- `fetch()` — gets a raw reading from its portal,
- `parse(reading)` — turns it into the shared `FlightStatus` (`models.py`),
- `history(directory)` — returns its `FlightHistory` (`flightlog.py`), which
  decides how readings are written and read back. Reuse `ChangeLog` for
  change-only JSON Lines, or implement your own format.

Same Wi-Fi system as an existing provider (e.g. another Gogo/Intelsat airline):
subclass it and set `id` and `name`, like `aircanada.py`. Then add an instance
to `PROVIDERS` in `providers/__init__.py`.

## Tests and lint

```bash
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/ruff format .
```

GitHub Actions (`.github/workflows/ci.yml`) runs the same lint plus tests on
Python 3.9–3.14 for every push to `main` and every pull request.
