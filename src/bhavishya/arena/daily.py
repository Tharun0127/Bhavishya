"""The daily forecast cycle: fetch, prepare model inputs, run models, commit hashed forecasts.

Directory layout on the data branch (``root``)::

    inputs/<run_date>/<source>.parquet     history given to models (truncated at cutoff)
    inputs/<run_date>/scales.parquet       MASE scales computed from that same history
    staging/<run_date>/<model>/<source>.*  model outputs before commit (not published)
    forecasts/<run_date>/forecasts.parquet all models, all sources: the committed file
    forecasts/<run_date>/run.json          cutoffs, model info, failures, input hashes
    manifest.csv                           append-only SHA-256 manifest
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from bhavishya.arena import health
from bhavishya.arena.hashing import append_manifest, ots_stamp, sha256_file
from bhavishya.arena.panel import Panel
from bhavishya.fetch import fetch_source
from bhavishya.http import PoliteClient
from bhavishya.models.base import HORIZON, truncate_history
from bhavishya.models.registry import MODELS, ModelSpec, python_for
from bhavishya.sources import get_source
from bhavishya.store import VintageStore

log = logging.getLogger(__name__)

#: A series whose last value is older than this many days before its source cutoff is skipped.
MAX_SERIES_LAG_DAYS = 2
#: A series needs at least this many days of history to be forecast.
MIN_HISTORY_DAYS = 90
#: How far back a live fetch looks for new or re-uploaded files.
LIVE_FETCH_DAYS = 10
SEASON = 7


@dataclass
class Prepared:
    run_date: pd.Timestamp
    cutoffs: dict[str, pd.Timestamp] = field(default_factory=dict)
    skipped_series: dict[str, str] = field(default_factory=dict)
    skipped_sources: dict[str, str] = field(default_factory=dict)
    filled_values: dict[str, int] = field(default_factory=dict)


def fetch_live(store: VintageStore, panel: Panel, run_date: pd.Timestamp) -> dict[str, health.SourceHealth]:
    """Fetch recent files for every panel source and judge each source's health."""
    client = PoliteClient()
    out = {}
    for source in panel.sources:
        start = run_date - pd.Timedelta(days=LIVE_FETCH_DAYS)
        try:
            res = fetch_source(get_source(source), start, run_date, client=client, store=store)
        except Exception as exc:  # never let one source stop the others
            log.exception("fetch of %s crashed", source)
            out[source] = health.SourceHealth(source, "failed", f"crash: {exc!r}")
            continue
        out[source] = health.judge(res, store.as_of(run_date, [source]), get_source(source), run_date)
    return out


def regularise(history: pd.DataFrame, cutoff: pd.Timestamp) -> tuple[pd.DataFrame, int]:
    """Daily grid from each series' first value to ``cutoff``; gaps filled with the last value.

    Forward fill is the simplest rule that uses no future data. The number of filled values is
    recorded so heavy filling is visible.
    """
    frames, filled = [], 0
    for sid, part in history.groupby("series_id", sort=True):
        idx = pd.date_range(part["timestamp"].min(), cutoff, freq="D")
        s = part.set_index("timestamp")["value"].reindex(idx)
        filled += int(s.isna().sum())
        frames.append(pd.DataFrame({"series_id": sid, "timestamp": idx, "value": s.ffill().to_numpy()}))
    return pd.concat(frames, ignore_index=True), filled


def mase_scales(history: pd.DataFrame) -> pd.DataFrame:
    """In-sample mean absolute seasonal difference per series, the MASE denominator."""

    def scale(values: pd.Series) -> float:
        return float(values.diff(SEASON).abs().mean())

    out = history.sort_values("timestamp").groupby("series_id")["value"].apply(scale).rename("mase_scale")
    return out.reset_index()


def prepare(store: VintageStore, panel: Panel, run_date: pd.Timestamp, unhealthy: set[str]) -> Prepared:
    """Write model inputs for ``run_date`` using only data with vintage <= run_date."""
    prep = Prepared(run_date)
    folder = store.root / "inputs" / f"{run_date:%Y-%m-%d}"
    folder.mkdir(parents=True, exist_ok=True)
    scales = []
    for source in panel.sources:
        if source in unhealthy:
            prep.skipped_sources[source] = "source unhealthy today"
            continue
        obs = store.as_of(run_date, [source])
        obs = obs[obs["series_id"].isin(panel.for_source(source)) & (obs["timestamp"] <= run_date)]
        if obs.empty:
            prep.skipped_sources[source] = "no data"
            continue
        cutoff = pd.Timestamp(obs["timestamp"].max())
        last = obs.groupby("series_id")["timestamp"].max()
        first = obs.groupby("series_id")["timestamp"].min()
        keep = []
        for sid in panel.for_source(source):
            if sid not in last.index:
                prep.skipped_series[sid] = "no data"
            elif (cutoff - last[sid]).days > MAX_SERIES_LAG_DAYS:
                prep.skipped_series[sid] = f"last value {last[sid]:%Y-%m-%d}, cutoff {cutoff:%Y-%m-%d}"
            elif (cutoff - first[sid]).days + 1 < MIN_HISTORY_DAYS:
                prep.skipped_series[sid] = "history shorter than 90 days"
            else:
                keep.append(sid)
        hist = truncate_history(obs[obs["series_id"].isin(keep)], cutoff)
        hist, filled = regularise(hist, cutoff)
        hist.to_parquet(folder / f"{source}.parquet", index=False)
        prep.cutoffs[source] = cutoff
        prep.filled_values[source] = filled
        scales.append(mase_scales(hist).assign(source=source, cutoff=cutoff))
    if scales:
        pd.concat(scales, ignore_index=True).to_parquet(folder / "scales.parquet", index=False)
    with (folder / "prepared.json").open("w", encoding="utf-8") as fh:
        json.dump(_prepared_json(prep), fh, indent=2, sort_keys=True)
    return prep


def _prepared_json(prep: Prepared) -> dict[str, object]:
    return {
        "run_date": f"{prep.run_date:%Y-%m-%d}",
        "cutoffs": {k: f"{v:%Y-%m-%d}" for k, v in prep.cutoffs.items()},
        "skipped_series": prep.skipped_series,
        "skipped_sources": prep.skipped_sources,
        "filled_values": prep.filled_values,
    }


def run_model(
    store: VintageStore, spec: ModelSpec, run_date: pd.Timestamp, python: str | None = None
) -> dict:
    """Run one model on every prepared source, each in a subprocess with a time limit."""
    folder = store.root / "inputs" / f"{run_date:%Y-%m-%d}"
    prepared = json.loads((folder / "prepared.json").read_text(encoding="utf-8"))
    stage = store.root / "staging" / f"{run_date:%Y-%m-%d}" / spec.name
    stage.mkdir(parents=True, exist_ok=True)
    status: dict[str, object] = {}
    for source, cutoff in prepared["cutoffs"].items():
        cmd = [
            python or python_for(spec.env),
            "-m",
            "bhavishya.models.run",
            "--model",
            spec.name,
            "--history",
            str(folder / f"{source}.parquet"),
            "--cutoff",
            cutoff,
            "--horizon",
            str(HORIZON),
            "--out",
            str(stage / f"{source}.parquet"),
            "--info",
            str(stage / f"{source}.json"),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=spec.timeout_s)
            ok = res.returncode == 0
            status[source] = "ok" if ok else f"exit {res.returncode}: {res.stderr.strip()[-500:]}"
        except subprocess.TimeoutExpired:
            status[source] = f"timeout after {spec.timeout_s}s"
        log.info("%s on %s: %s", spec.name, source, str(status[source])[:200])
    (stage / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


def commit_forecasts(store: VintageStore, run_date: pd.Timestamp, stamp: bool = True) -> Path | None:
    """Merge staged outputs into one forecast file, hash it, and append it to the manifest."""
    day = f"{run_date:%Y-%m-%d}"
    stage = store.root / "staging" / day
    inputs = store.root / "inputs" / day
    frames, models, failures = [], {}, {}
    for model_dir in sorted(p for p in stage.iterdir() if p.is_dir()) if stage.exists() else []:
        if not (model_dir / "status.json").exists():
            failures[model_dir.name] = "model crashed before writing a status"
            continue
        status = json.loads((model_dir / "status.json").read_text(encoding="utf-8"))
        for source, state in status.items():
            if state != "ok":
                failures[f"{model_dir.name}/{source}"] = state
                continue
            fc = pd.read_parquet(model_dir / f"{source}.parquet")
            fc.insert(0, "source", source)
            fc.insert(0, "model", model_dir.name)
            frames.append(fc)
            models[f"{model_dir.name}/{source}"] = json.loads(
                (model_dir / f"{source}.json").read_text("utf-8")
            )
    if not frames:
        log.error("no successful model output for %s", day)
        return None
    out_dir = store.root / "forecasts" / day
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "forecasts.parquet"
    if path.exists():
        raise FileExistsError(f"{path} exists; forecasts are never overwritten")
    forecasts = pd.concat(frames, ignore_index=True)
    forecasts["run_date"] = run_date
    forecasts.to_parquet(path, index=False, compression="zstd")
    prepared = json.loads((inputs / "prepared.json").read_text(encoding="utf-8"))
    run = {
        **prepared,
        "models": models,
        "failures": failures,
        "input_sha256": {p.name: sha256_file(p) for p in sorted(inputs.glob("*.parquet"))},
        "forecasts_sha256": sha256_file(path),
        "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    (out_dir / "run.json").write_text(json.dumps(run, indent=2, sort_keys=True), encoding="utf-8")
    append_manifest(
        store.root,
        {
            "run_date": day,
            "path": path.relative_to(store.root).as_posix(),
            "sha256": run["forecasts_sha256"],
            "n_rows": len(forecasts),
            "models": ";".join(sorted(forecasts["model"].unique())),
            "created_at_utc": run["created_at_utc"],
        },
    )
    if stamp:
        ots_stamp(path)
    return path


def daily(
    store: VintageStore,
    panel: Panel,
    run_date: pd.Timestamp,
    *,
    live: bool,
    models: list[str] | None = None,
    stamp: bool = True,
) -> Path | None:
    """Full cycle in one process. CI splits these steps into separate jobs."""
    unhealthy: set[str] = set()
    if live:
        report = fetch_live(store, panel, run_date)
        health.record(store.root, run_date, report)
        unhealthy = {s for s, h in report.items() if h.state != "ok"}
    prepare(store, panel, run_date, unhealthy)
    for name in models or list(MODELS):
        try:
            run_model(store, MODELS[name], run_date)
        except Exception:  # a broken model must not stop the others
            log.exception("model %s failed before running", name)
    return commit_forecasts(store, run_date, stamp=stamp)
