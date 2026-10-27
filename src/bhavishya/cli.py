"""Command line entry point: ``bhavishya <command>``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from bhavishya.fetch import fetch_source, today_ist
from bhavishya.http import PoliteClient
from bhavishya.sources import get_source
from bhavishya.store import VintageStore


def _cmd_backfill(args: argparse.Namespace) -> int:
    store = VintageStore(Path(args.data_dir))
    client = PoliteClient()
    end = pd.Timestamp(args.end) if args.end else today_ist()
    for name in args.sources:
        res = fetch_source(
            get_source(name), pd.Timestamp(args.start), end, client=client, store=store, backfill=True
        )
        print(
            f"{name}: ok_files={res.ok_files} missing={len(res.missing_files)} "
            f"errors={len(res.errors)} contract_errors={len(res.contract_errors)}"
        )
        for msg in (res.errors + res.contract_errors)[:10]:
            print("  ", msg)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bhavishya", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("backfill", help="download history, stamped with the source's publication dates")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end")
    p.add_argument("--sources", nargs="+", default=["grid_india", "cpcb_aqi"])
    p.set_defaults(func=_cmd_backfill)

    # Arena commands live in their own module so the data package does not import model code.
    from bhavishya.arena.cli import add_arena_commands

    add_arena_commands(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
