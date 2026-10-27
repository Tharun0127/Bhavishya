"""Aggregate scores into skill relative to seasonal naive, with bootstrap intervals.

Skill for model M on a set of forecasts:

1. Keep only forecasts that M and the reference both made (same series, run date, horizon).
2. For each series, divide M's mean metric by the reference's mean metric.
3. Take the geometric mean of these ratios across series.

Below 1 means better than seasonal naive. The geometric mean treats a halving and a doubling
symmetrically and stops one large series from dominating. Intervals come from resampling whole
run dates (block bootstrap), because errors on the same day are correlated across series.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bhavishya.models.registry import REFERENCE_MODEL

KEY = ["series_id", "run_date", "horizon"]
#: A model is ranked only after this many scored forecasts and this many days live.
MIN_SCORED = 10_000
MIN_DAYS_LIVE = 28
N_BOOT = 1000


@dataclass(frozen=True)
class Skill:
    value: float
    lo: float
    hi: float
    n_series: int


def paired(scores: pd.DataFrame, model: str, metric: str, ref: str = REFERENCE_MODEL) -> pd.DataFrame:
    """Rows where both ``model`` and ``ref`` have a finite ``metric``, side by side."""
    a = scores.loc[scores["model"] == model, [*KEY, metric]].rename(columns={metric: "m"})
    b = scores.loc[scores["model"] == ref, [*KEY, metric]].rename(columns={metric: "r"})
    both = a.merge(b, on=KEY)
    return both[np.isfinite(both["m"]) & np.isfinite(both["r"])]


def _geo_ratio(both: pd.DataFrame) -> tuple[float, int]:
    per_series = both.groupby("series_id")[["m", "r"]].mean()
    per_series = per_series[(per_series["m"] > 0) & (per_series["r"] > 0)]
    if per_series.empty:
        return float("nan"), 0
    return float(np.exp(np.log(per_series["m"] / per_series["r"]).mean())), len(per_series)


def relative_skill(
    scores: pd.DataFrame,
    model: str,
    metric: str,
    ref: str = REFERENCE_MODEL,
    n_boot: int = N_BOOT,
    seed: int = 0,
) -> Skill:
    both = paired(scores, model, metric, ref)
    value, n_series = _geo_ratio(both)
    if not n_series:
        return Skill(float("nan"), float("nan"), float("nan"), 0)
    days = both["run_date"].unique()
    by_day = {d: g for d, g in both.groupby("run_date")}
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(n_boot):
        sample = rng.choice(days, size=len(days), replace=True)
        draws.append(_geo_ratio(pd.concat([by_day[d] for d in sample], ignore_index=True))[0])
    lo, hi = np.nanpercentile(draws, [2.5, 97.5]) if len(days) > 1 else (float("nan"), float("nan"))
    return Skill(value, float(lo), float(hi), n_series)


def leaderboard(scores: pd.DataFrame, forecasts_days: dict[str, int], n_boot: int = N_BOOT) -> pd.DataFrame:
    """One row per model: days live, scored count, skill with 95% intervals, coverage, rank."""
    rows = []
    for model, part in scores.groupby("model"):
        crps = relative_skill(scores, str(model), "scaled_crps", n_boot=n_boot)
        mase = relative_skill(scores, str(model), "mase", n_boot=n_boot)
        n_scored = len(part)
        days_live = forecasts_days.get(str(model), 0)
        rows.append(
            {
                "model": model,
                "days_live": days_live,
                "n_scored": n_scored,
                "crps_skill": crps.value,
                "crps_lo": crps.lo,
                "crps_hi": crps.hi,
                "mase_skill": mase.value,
                "mase_lo": mase.lo,
                "mase_hi": mase.hi,
                "coverage_80": float(part["covered_80"].mean()),
                "mean_mase": float(part["mase"].mean()),
                "eligible": n_scored >= MIN_SCORED and days_live >= MIN_DAYS_LIVE,
            }
        )
    board = pd.DataFrame(rows)
    if board.empty:
        return board
    board = board.sort_values("crps_skill").reset_index(drop=True)
    board["rank"] = np.nan
    eligible = board["eligible"]
    board.loc[eligible, "rank"] = np.arange(1, int(eligible.sum()) + 1)
    return board


def breakdown(scores: pd.DataFrame, by: str, n_boot: int = 200) -> pd.DataFrame:
    """Skill per model within each value of ``by`` (``source`` or ``horizon_bucket``)."""
    rows = []
    for value, part in scores.groupby(by):
        for model in sorted(part["model"].unique()):
            s = relative_skill(part, model, "scaled_crps", n_boot=n_boot)
            rows.append(
                {
                    by: value,
                    "model": model,
                    "crps_skill": s.value,
                    "crps_lo": s.lo,
                    "crps_hi": s.hi,
                    "coverage_80": float(part.loc[part["model"] == model, "covered_80"].mean()),
                    "n_scored": int((part["model"] == model).sum()),
                }
            )
    return pd.DataFrame(rows)


def per_series(scores: pd.DataFrame) -> pd.DataFrame:
    """Mean scaled CRPS, MASE and coverage per model and series (no bootstrap)."""
    return (
        scores.groupby(["series_id", "model"])
        .agg(
            mean_scaled_crps=("scaled_crps", "mean"),
            mean_mase=("mase", "mean"),
            coverage_80=("covered_80", "mean"),
            n_scored=("mase", "size"),
        )
        .reset_index()
    )
