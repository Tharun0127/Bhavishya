"""End-to-end PIPELINE TEST. Not benchmark results.

Replays past dates as if each were "today", using only stored vintages on or before that date,
and runs the full cycle: prepare -> all models -> commit with hashes -> score -> verify -> site.
It writes to a separate scratch store so nothing reaches the real arena record.

    python scripts/pipeline_test.py --source-store arena-data --out pipeline-test \
        --dates 2026-09-20 2026-10-01 2026-10-10

Scores printed here are from replayed dates and must never be presented as arena results.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

from bhavishya.arena import daily
from bhavishya.arena.hashing import read_manifest, verify_manifest
from bhavishya.arena.panel import load_panel
from bhavishya.arena.scoring import score_all
from bhavishya.arena.site import build_site
from bhavishya.store import VintageStore

BANNER = "PIPELINE TEST (replayed dates; not benchmark results)"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--source-store", default="arena-data")
    p.add_argument("--out", default="pipeline-test")
    p.add_argument("--dates", nargs="+", required=True)
    p.add_argument("--models", nargs="+")
    p.add_argument("--panel", default="config/panel.yaml")
    args = p.parse_args()

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    store_dir = out / "store"
    # Copy only observations and the raw index: what the arena knew, with vintages.
    shutil.copytree(Path(args.source_store) / "observations", store_dir / "observations")
    shutil.copy(Path(args.source_store) / "raw_index.csv", store_dir / "raw_index.csv")
    store = VintageStore(store_dir)
    panel = load_panel(args.panel)

    report: dict[str, object] = {"banner": BANNER, "runs": {}}
    for day in args.dates:
        run_date = pd.Timestamp(day)
        path = daily.daily(store, panel, run_date, live=False, models=args.models, stamp=False)
        run = json.loads((path.parent / "run.json").read_text(encoding="utf-8")) if path else {}
        # Leakage check on what was actually written: no input row after its cutoff or vintage date.
        inputs = store.root / "inputs" / day
        for src, cutoff in run.get("cutoffs", {}).items():
            hist = pd.read_parquet(inputs / f"{src}.parquet")
            assert hist["timestamp"].max() == pd.Timestamp(cutoff), "input does not end at cutoff"
            assert pd.Timestamp(cutoff) <= run_date, "cutoff after run date"
        report["runs"][day] = {  # type: ignore[index]
            "committed": bool(path),
            "cutoffs": run.get("cutoffs"),
            "failures": run.get("failures"),
            "models": sorted({k.split("/")[0] for k in run.get("models", {})}),
            "skipped_series": len(run.get("skipped_series", {})),
            "filled_values": run.get("filled_values"),
        }

    problems = verify_manifest(store.root)
    scored = score_all(store)
    build_site(store, panel, Path("docs"), out / "_site")
    report["manifest_rows"] = len(read_manifest(store.root))
    report["verify_problems"] = problems
    report["scored_rows"] = len(scored)
    if len(scored):
        report["scored_by_model"] = scored.groupby("model").size().to_dict()
        report["coverage_80_by_model"] = scored.groupby("model")["covered_80"].mean().round(3).to_dict()
    report["site_pages"] = len(list((out / "_site").rglob("*.html")))
    (out / "pipeline_test_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(BANNER)
    print(json.dumps(report, indent=2, default=str))
    return 0 if not problems and all(r["committed"] for r in report["runs"].values()) else 1  # type: ignore[union-attr]


if __name__ == "__main__":
    sys.exit(main())
