"""Score committed forecasts against the first-released actual values.

Why the first release: it is the value that existed when the outcome first became public.
Scoring against later revisions would mix forecast error with revision noise and would let
results drift after the fact. Revisions are kept in the store and can be studied separately.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from bhavishya.arena.hashing import ots_upgrade, read_manifest, sha256_file
from bhavishya.models.base import QUANTILE_COLUMNS, QUANTILES
from bhavishya.sources import SOURCES
from bhavishya.store import VintageStore

log = logging.getLogger(__name__)

TAUS = np.asarray(QUANTILES)


def pinball(y: np.ndarray, q: np.ndarray, tau: np.ndarray) -> np.ndarray:
    """Pinball (quantile) loss. ``y`` is (n,), ``q`` is (n, k), ``tau`` is (k,)."""
    diff = y[:, None] - q
    return np.maximum(tau * diff, (tau - 1.0) * diff)


def crps_from_quantiles(y: np.ndarray, q: np.ndarray, tau: np.ndarray = TAUS) -> np.ndarray:
    """Quantile approximation of CRPS: the mean over levels of twice the pinball loss.

    With 9 evenly spaced levels this is the standard discrete approximation used by GluonTS
    and fev ("mean weighted quantile loss" before normalisation).
    """
    return 2.0 * pinball(y, q, tau).mean(axis=1)


def covered(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    return (y >= lo) & (y <= hi)


def score_frame(forecasts: pd.DataFrame, actuals: pd.DataFrame, scales: pd.DataFrame) -> pd.DataFrame:
    """Join forecasts to actuals and scales, and compute per-forecast metrics.

    ``actuals`` has ``series_id, timestamp, value, vintage_date`` (first release).
    ``scales`` has ``run_date, series_id, mase_scale``.
    """
    act = actuals.rename(
        columns={"timestamp": "target_date", "value": "actual", "vintage_date": "actual_vintage"}
    )
    df = forecasts.merge(
        act[["series_id", "target_date", "actual", "actual_vintage"]],
        on=["series_id", "target_date"],
        how="inner",
    )
    df = df.merge(scales[["run_date", "series_id", "mase_scale"]], on=["run_date", "series_id"], how="left")
    df["prospective"] = is_prospective(df)
    y = df["actual"].to_numpy(dtype="float64")
    q = df[list(QUANTILE_COLUMNS)].to_numpy(dtype="float64")
    scale = df["mase_scale"].to_numpy(dtype="float64")
    # A flat history has scale 0; scaled metrics are undefined there and are left as NaN.
    scale = np.where(scale > 0, scale, np.nan)
    df["abs_error"] = np.abs(y - df["q0.5"].to_numpy())
    df["mase"] = df["abs_error"] / scale
    df["crps"] = crps_from_quantiles(y, q)
    df["scaled_crps"] = df["crps"] / scale
    df["covered_80"] = covered(y, df["q0.1"].to_numpy(), df["q0.9"].to_numpy())
    df["horizon_bucket"] = pd.cut(df["horizon"], [0, 7, 14, 28], labels=["1-7", "8-14", "15-28"]).astype(str)
    return df


def target_exists_from(source: pd.Series, target_date: pd.Series) -> pd.Series:
    """Earliest UTC instant at which the value for ``target_date`` could exist at the source."""
    hours = source.map(lambda s: SOURCES[s].info.complete_after_hours if s in SOURCES else 24.0)
    ist = target_date + pd.to_timedelta(hours, unit="h")
    return (ist - pd.Timedelta(hours=5, minutes=30)).dt.tz_localize("UTC")


def is_prospective(df: pd.DataFrame) -> pd.Series:
    """True when the forecast was committed before its target value could exist.

    Two checks. Time: the commit time is before the instant the target period ended at the source
    (16:00 IST for CPCB's 24-hour average, midnight for Grid-India's daily totals). Dates alone are
    not enough: CPCB publishes day D's value on day D itself. Vintage: the stored actual was not
    published before the run date. Rows failing either check are dropped from scoring.
    """
    committed = pd.to_datetime(df["committed_at"], utc=True)
    before_target = committed < target_exists_from(df["source"], df["target_date"])
    return before_target & (df["actual_vintage"] >= df["run_date"])


def load_committed(root: Path, verify: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """All forecast files listed in the manifest (hash-checked) and their MASE scales."""
    frames, scale_frames = [], []
    for row in read_manifest(root).itertuples():
        path = root / str(row.path)
        if verify and sha256_file(path) != row.sha256:
            raise RuntimeError(f"{row.path} does not match its manifest hash; refusing to score")
        frames.append(pd.read_parquet(path).assign(committed_at=pd.Timestamp(str(row.created_at_utc))))
        sp = root / "inputs" / str(row.run_date) / "scales.parquet"
        if sp.exists():
            scale_frames.append(pd.read_parquet(sp).assign(run_date=pd.Timestamp(str(row.run_date))))
    if not frames:
        return pd.DataFrame(), pd.DataFrame(columns=["run_date", "series_id", "mase_scale"])
    return pd.concat(frames, ignore_index=True), pd.concat(scale_frames, ignore_index=True)


def score_all(store: VintageStore, out: Path | None = None) -> pd.DataFrame:
    """Rebuild ``scores/scores.parquet`` from every committed forecast that now has an actual."""
    forecasts, scales = load_committed(store.root)
    if forecasts.empty:
        return pd.DataFrame()
    actuals = store.first_release(sorted(forecasts["source"].unique()))
    scored = score_frame(forecasts, actuals, scales)
    dropped = int((~scored["prospective"]).sum())
    if dropped:
        log.warning("dropped %d non-prospective rows", dropped)
    scored = scored[scored["prospective"]].drop(columns="prospective")
    out = out or store.root / "scores" / "scores.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    scored.to_parquet(out, index=False, compression="zstd")
    for proof in (store.root / "forecasts").glob("*/*.ots"):
        ots_upgrade(proof)
    return scored
