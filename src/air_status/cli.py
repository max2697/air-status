"""Command line: `air-status` (live view) and `air-status history`."""

import argparse
from pathlib import Path
from typing import Optional

from rich.console import Console

from air_status import __version__
from air_status.flight_map import FlightMap
from air_status.providers import DEFAULT_PROVIDER, PROVIDERS, get_provider
from air_status.tui import Poller, history_table, run_live


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="air-status", description="Live in-flight status with map and history.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--data-dir", type=Path, default=Path.cwd(), help="folder for history/ and mapdata/ (default: current folder)"
    )
    sub = parser.add_subparsers(dest="command")
    live = sub.add_parser("live", help="live view, saves history (default)")
    live.add_argument(
        "-p",
        "--provider",
        choices=sorted(PROVIDERS),
        default=DEFAULT_PROVIDER,
        help=f"airline / Wi-Fi system (default: {DEFAULT_PROVIDER})",
    )
    live.add_argument(
        "--every", type=int, metavar="SECONDS", help="refresh interval (default: the provider's own update rate)"
    )
    sub.add_parser("history", help="list saved flights")
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    history_dir = args.data_dir / "history"
    try:
        if args.command == "history":
            table = history_table([p.history(history_dir / p.id) for p in PROVIDERS.values()])
            if table is None:
                print("No saved flights yet.")
            else:
                Console().print(table)
                print(f"Files: {history_dir}")
        else:
            provider = get_provider(getattr(args, "provider", DEFAULT_PROVIDER))
            every = getattr(args, "every", None) or provider.update_interval
            poller = Poller(provider, provider.history(history_dir / provider.id), every)
            run_live(poller, FlightMap(args.data_dir / "mapdata"))
    except KeyboardInterrupt:
        pass
