"""Flight history. Each provider decides how its readings are stored.

FlightHistory is what the app needs from any history: save a reading, list the
files, and load a file back as FlightStatus objects. ChangeLog is a ready-made
format that providers can reuse: compact JSON Lines where the first line holds
the full record and each later line only the fields that changed. Readings with
no changes are not written.
"""

import json
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from air_status.models import FlightStatus

Flat = dict[str, Any]
_MISSING = object()


def flatten(d: dict[str, Any], prefix: str = "") -> Flat:
    out: Flat = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flatten(v, f"{prefix}{k}."))
        else:
            out[prefix + k] = v
    return out


def unflatten(flat: Flat) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, v in flat.items():
        node = out
        *parents, last = key.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        node[last] = v
    return out


class FlightHistory(ABC):
    """History of one provider's flights in one directory, one file per flight."""

    suffix = ".jsonl"

    def __init__(self, directory: Path):
        self.directory = directory

    @abstractmethod
    def path_for(self, reading: Any) -> Path:
        """File that holds the flight this reading belongs to."""

    @abstractmethod
    def save(self, reading: Any) -> bool:
        """Store a raw provider reading. Returns True if anything was written."""

    @abstractmethod
    def load(self, path: Path) -> list[FlightStatus]:
        """Every saved status of one flight, oldest first."""

    def files(self) -> list[Path]:
        return sorted(self.directory.glob(f"*{self.suffix}"))

    def track(self, reading: Any) -> list[FlightStatus]:
        """Saved history of the flight this reading belongs to (empty if none)."""
        path = self.path_for(reading)
        return self.load(path) if path.exists() else []


class ChangeLog(FlightHistory):
    """Change-only JSON Lines. Subclasses say what to store and how to read it back."""

    @abstractmethod
    def to_record(self, reading: Any) -> dict[str, Any]:
        """What to store for a reading (nested dicts are fine)."""

    @abstractmethod
    def from_record(self, record: dict[str, Any]) -> FlightStatus:
        """Turn a stored record (nested again) back into a FlightStatus."""

    def __init__(self, directory: Path):
        super().__init__(directory)
        self._cache: dict[Path, tuple[int, Flat]] = {}  # path -> (file size, last state)

    @staticmethod
    def _replay(path: Path) -> Iterator[Flat]:
        """Yield the full flat record after each line."""
        state: Flat = {}
        with open(path) as fh:
            for line in fh:
                if line.strip():
                    state.update(json.loads(line))
                    yield dict(state)

    def _last_state(self, path: Path) -> Flat:
        size = path.stat().st_size if path.exists() else 0
        cached = self._cache.get(path)
        if cached and cached[0] == size:
            return cached[1]
        # First save, or another process wrote to the file meanwhile
        if not size:
            return {}
        last = deque(self._replay(path), maxlen=1)
        return last[0] if last else {}

    def save(self, reading: Any) -> bool:
        path = self.path_for(reading)
        state = self._last_state(path)
        new = flatten(self.to_record(reading))
        changes = {k: v for k, v in new.items() if state.get(k, _MISSING) != v}
        if not changes:
            return False
        self.directory.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(changes, separators=(",", ":")) + "\n")
        self._cache[path] = (path.stat().st_size, {**state, **changes})
        return True

    def load(self, path: Path) -> list[FlightStatus]:
        return [self.from_record(unflatten(s)) for s in self._replay(path)]
