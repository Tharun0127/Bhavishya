"""Arena sub-commands of the ``bhavishya`` CLI.

The daily CI job runs ``fetch``, ``prepare``, ``run-model`` (one job per model) and ``commit``.
``daily`` runs the same steps in one process, for local use and for replay tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import yaml

from bhavishya.fetch import today_ist
from bhavishya.store import VintageStore

if TYPE_CHECKING:
    from bhavishya.arena.panel import Panel


def _store(args: argparse.Namespace) -> VintageStore:
    return VintageStore(Path(args.data_dir))


def _date(value: str | None) -> pd.Timestamp:
    return pd.Timestamp(value).normalize() if value else today_ist()


def _panel(args: argparse.Namespace) -> Panel:
    from bhavishya.arena.panel import load_panel

    return load_panel(args.panel)


def cmd_fetch(args: argparse.Namespace) -> int:
    from bhavishya.arena import daily, health

    run_date = _date(args.run_date)
    report = daily.fetch_live(_store(args), _panel(args), run_date)
    health.record(_store(args).root, run_date, report)
    for h in report.values():
        print(f"{h.source}: {h.state} {h.detail[:200]}")
    return 0  # unhealthy sources are reported, not fatal: the others must still run


def cmd_prepare(args: argparse.Namespace) -> int:
    from bhavishya.arena import daily

    store, run_date = _store(args), _date(args.run_date)
    issues = store.root / "health" / "open_issues"
    unhealthy = {p.stem for p in issues.glob("*.md")} if args.respect_health and issues.exists() else set()
    prep = daily.prepare(store, _panel(args), run_date, unhealthy)
    print(json.dumps(daily._prepared_json(prep), indent=2))
    return 0 if prep.cutoffs else 1


def cmd_run_model(args: argparse.Namespace) -> int:
    from bhavishya.arena import daily
    from bhavishya.models.registry import MODELS

    status = daily.run_model(_store(args), MODELS[args.model], _date(args.run_date), python=args.python)
    print(json.dumps(status, indent=2))
    return 0


def cmd_run_submission(args: argparse.Namespace) -> int:
    from bhavishya.arena.submissions import run_submission

    status = run_submission(_store(args).root, Path(args.path), _date(args.run_date), build=not args.no_build)
    print(json.dumps(status, indent=2))
    return 0 if all(v == "ok" for v in status.values()) else 1


def cmd_commit(args: argparse.Namespace) -> int:
    from bhavishya.arena import daily

    path = daily.commit_forecasts(_store(args), _date(args.run_date), stamp=not args.no_stamp)
    print(path or "nothing committed")
    return 0 if path else 1


def cmd_daily(args: argparse.Namespace) -> int:
    from bhavishya.arena import daily

    path = daily.daily(
        _store(args),
        _panel(args),
        _date(args.run_date),
        live=not args.replay,
        models=args.models,
        stamp=not args.no_stamp,
    )
    print(path or "nothing committed")
    return 0 if path else 1


def cmd_score(args: argparse.Namespace) -> int:
    from bhavishya.arena.scoring import score_all

    scored = score_all(_store(args))
    print(f"scored rows: {len(scored)}")
    return 0


def cmd_site(args: argparse.Namespace) -> int:
    from bhavishya.arena.site import build_site

    build_site(_store(args), _panel(args), Path(args.docs), Path(args.out))
    print(f"site written to {args.out}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from bhavishya.arena.hashing import verify_manifest

    problems = verify_manifest(_store(args).root)
    for p in problems:
        print("FAIL", p)
    print("all forecast files match the manifest" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


def cmd_select_panel(args: argparse.Namespace) -> int:
    from bhavishya.arena.panel import select_panel

    store, frozen = _store(args), _date(args.frozen_on)
    chosen, stats = select_panel(store.as_of(frozen, ["grid_india", "cpcb_aqi"]), frozen)
    doc = yaml.safe_load(Path(args.rules).read_text(encoding="utf-8"))
    doc.update(
        {
            "frozen_on": f"{frozen:%Y-%m-%d}",
            "series": chosen,
            "selection_stats": {
                k: {
                    "coverage": round(float(v.coverage), 3),
                    "mean_value": round(float(v.mean_value), 2),
                    "selected": bool(v.selected),
                }
                for k, v in stats.iterrows()
            },
        }
    )
    Path(args.panel).write_text(yaml.safe_dump(doc, sort_keys=False, width=110), encoding="utf-8")
    print(f"{len(chosen)} series written to {args.panel}")
    return 0


def add_arena_commands(sub: argparse._SubParsersAction) -> None:
    def add(
        name: str, func: Callable[[argparse.Namespace], int], help_: str, run_date: bool = True
    ) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--data-dir", default="arena-data")
        p.add_argument("--panel", default="config/panel.yaml")
        if run_date:
            p.add_argument("--run-date", help="IST date, default today")
        p.set_defaults(func=func)
        return p

    add("fetch", cmd_fetch, "fetch new files for panel sources and record source health")
    p = add("prepare", cmd_prepare, "write model inputs truncated at each source's cutoff")
    p.add_argument("--respect-health", action="store_true", help="skip sources with an open health issue")
    p = add("run-model", cmd_run_model, "run one model on prepared inputs (in a subprocess)")
    p.add_argument("--model", required=True)
    p.add_argument("--python", help="interpreter to use instead of the model's default environment")
    p = add("run-submission", cmd_run_submission, "build and run a submission in a sandboxed container")
    p.add_argument("--path", required=True)
    p.add_argument("--no-build", action="store_true")
    p = add("commit", cmd_commit, "merge model outputs, hash, append to manifest, timestamp")
    p.add_argument("--no-stamp", action="store_true")
    p = add("daily", cmd_daily, "fetch, prepare, run all models, commit")
    p.add_argument("--replay", action="store_true", help="no live fetch; use stored vintages only")
    p.add_argument("--models", nargs="+")
    p.add_argument("--no-stamp", action="store_true")
    add("score", cmd_score, "score committed forecasts against first-released actuals", run_date=False)
    p = add("site", cmd_site, "build the static site", run_date=False)
    p.add_argument("--docs", default="docs")
    p.add_argument("--out", default="_site")
    add("verify", cmd_verify, "recompute every forecast file hash", run_date=False)
    p = add(
        "select-panel",
        cmd_select_panel,
        "apply the panel rules to data as of the freeze date",
        run_date=False,
    )
    p.add_argument("--frozen-on", required=True)
    p.add_argument("--rules", default="config/panel_rules.yaml")


if __name__ == "__main__":
    sys.exit(0)
