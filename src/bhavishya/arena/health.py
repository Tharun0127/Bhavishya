"""Source health checks, the gap log, and the status summary used by the status page.

A source is skipped for the day if it failed to download, broke its contract, or returned
stale data. Each skip is a recorded gap and produces an issue body that CI files on GitHub.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from bhavishya.fetch import FetchResult
from bhavishya.sources.base import Source

HEALTH_FIELDS = ("run_date", "source", "state", "detail", "newest_timestamp")


@dataclass
class SourceHealth:
    source: str
    state: str  # ok | failed | contract | stale
    detail: str = ""
    newest_timestamp: str = ""


def judge(result: FetchResult, as_of: pd.DataFrame, source: Source, run_date: pd.Timestamp) -> SourceHealth:
    newest = as_of["timestamp"].max() if not as_of.empty else pd.NaT
    newest_s = "" if pd.isna(newest) else f"{newest:%Y-%m-%d}"
    if result.errors:
        return SourceHealth(source.name, "failed", "; ".join(result.errors)[:1000], newest_s)
    if result.contract_errors:
        return SourceHealth(source.name, "contract", "; ".join(result.contract_errors)[:1000], newest_s)
    if pd.isna(newest) or (run_date - newest).days > source.contract.max_staleness_days:
        return SourceHealth(
            source.name,
            "stale",
            f"newest value {newest_s or 'none'} on run date "
            f"{run_date:%Y-%m-%d}; limit {source.contract.max_staleness_days} days",
            newest_s,
        )
    return SourceHealth(source.name, "ok", f"{result.ok_files} new file(s)", newest_s)


def record(root: Path, run_date: pd.Timestamp, report: dict[str, SourceHealth]) -> None:
    """Append today's health to the log and write an issue body for each unhealthy source."""
    path = root / "health" / "source_health.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEALTH_FIELDS, lineterminator="\n")
        if new:
            writer.writeheader()
        for h in report.values():
            writer.writerow(
                {
                    "run_date": f"{run_date:%Y-%m-%d}",
                    "source": h.source,
                    "state": h.state,
                    "detail": h.detail,
                    "newest_timestamp": h.newest_timestamp,
                }
            )
    issues = root / "health" / "open_issues"
    issues.mkdir(parents=True, exist_ok=True)
    for old in issues.glob("*.md"):
        old.unlink()
    for h in report.values():
        if h.state != "ok":
            (issues / f"{h.source}.md").write_text(issue_body(h, run_date), encoding="utf-8")


def issue_title(source: str) -> str:
    # Stable title so CI can find an existing open issue instead of filing duplicates.
    return f"Source health: {source} skipped"


def issue_body(h: SourceHealth, run_date: pd.Timestamp) -> str:
    return (
        f"The daily pipeline skipped `{h.source}` on {run_date:%Y-%m-%d}.\n\n"
        f"- State: `{h.state}`\n- Newest value: {h.newest_timestamp or 'none'}\n- Detail: {h.detail}\n\n"
        "Other sources and models ran normally. The skip is recorded as a gap in "
        "`health/source_health.csv` on the data branch. Close this issue when the source recovers.\n"
    )


def build_status(root: Path) -> dict[str, Any]:
    """Last successful run per source and per model, for the status page."""
    status: dict[str, Any] = {"sources": {}, "models": {}}
    hpath = root / "health" / "source_health.csv"
    if hpath.exists():
        log = pd.read_csv(hpath, dtype=str)
        for source, part in log.groupby("source"):
            ok = part[part["state"] == "ok"]
            last = part.iloc[-1]
            status["sources"][str(source)] = {
                "last_success": ok["run_date"].max() if len(ok) else None,
                "last_state": last["state"],
                "last_detail": last["detail"],
                "newest_value": last["newest_timestamp"],
                "gaps_last_30_runs": int((part.tail(30)["state"] != "ok").sum()),
            }
    for run_file in sorted((root / "forecasts").glob("*/run.json")) if (root / "forecasts").exists() else []:
        run = json.loads(run_file.read_text(encoding="utf-8"))
        day = run["run_date"]
        for key in run.get("models", {}):
            model = key.split("/")[0]
            entry = status["models"].setdefault(
                model, {"last_success": None, "last_failure": None, "detail": ""}
            )
            entry["last_success"] = day
        for key, why in run.get("failures", {}).items():
            model = key.split("/")[0]
            entry = status["models"].setdefault(
                model, {"last_success": None, "last_failure": None, "detail": ""}
            )
            entry["last_failure"], entry["detail"] = day, f"{key}: {why}"[:300]
    status["generated_at_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
    return status
