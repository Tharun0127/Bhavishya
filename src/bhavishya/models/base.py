"""The single interface every arena model implements, and the leakage guard around it.

A model receives a history frame (``series_id, timestamp, value``) that ends at ``cutoff`` and
returns quantile forecasts for horizons ``1..H`` days after the cutoff. Models never see the
data store, the run date, or anything after the cutoff. The runner enforces this twice:
it truncates history before writing it to the model's input file (models/run.py), and
:meth:`Forecaster.forecast` refuses history that extends past the cutoff.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

QUANTILES: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
QUANTILE_COLUMNS: tuple[str, ...] = tuple(f"q{q:.1f}" for q in QUANTILES)
HORIZON = 28
HISTORY_COLUMNS = ("series_id", "timestamp", "value")
FORECAST_COLUMNS = ("series_id", "cutoff", "horizon", "target_date", *QUANTILE_COLUMNS)

#: Central intervals whose endpoints are the 9 quantiles. Models that produce prediction
#: intervals (statsforecast, mlforecast) map level L to quantiles (1-L/100)/2 and (1+L/100)/2.
LEVELS: tuple[int, ...] = (20, 40, 60, 80)


class LeakageError(RuntimeError):
    """Raised when a model would see data after its cutoff."""


@dataclass
class ModelInfo:
    """Facts recorded next to every forecast so results can be reproduced and audited."""

    name: str
    family: str  # "baseline" or "foundation" or "submission"
    version: str  # package version or submission version
    weights_repo: str | None = None
    weights_revision: str | None = None
    weights_sha256: str | None = None
    config: dict[str, Any] = field(default_factory=dict)

    def config_hash(self) -> str:
        blob = json.dumps(self.config, sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:16]


def check_no_leakage(history: pd.DataFrame, cutoff: pd.Timestamp) -> None:
    """Raise :class:`LeakageError` if any history row is after ``cutoff``."""
    latest = history["timestamp"].max()
    if pd.notna(latest) and latest > cutoff:
        raise LeakageError(f"history reaches {latest:%Y-%m-%d}, after cutoff {cutoff:%Y-%m-%d}")


def truncate_history(history: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Keep only rows at or before ``cutoff``, sorted, with the three model columns."""
    out = history.loc[history["timestamp"] <= cutoff, list(HISTORY_COLUMNS)]
    return out.sort_values(["series_id", "timestamp"]).reset_index(drop=True)


class Forecaster(ABC):
    """Base class for arena models. Subclasses implement :meth:`_predict` only."""

    #: Upper bound on history length passed to the model, in days. Long enough for yearly
    #: seasonality, short enough to keep CPU runs inside GitHub Actions limits.
    max_history_days: int = 1024

    @abstractmethod
    def info(self) -> ModelInfo:
        """Describe the model, including pinned weights and their hash."""

    @abstractmethod
    def _predict(self, history: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Return columns ``series_id, horizon, q0.1 ... q0.9`` for horizons ``1..horizon``.

        ``history`` is regular daily data without gaps, ending on the same date for all series.
        """

    def forecast(self, history: pd.DataFrame, cutoff: pd.Timestamp, horizon: int = HORIZON) -> pd.DataFrame:
        """Validate inputs, call the model, validate and label its outputs."""
        check_no_leakage(history, cutoff)
        start = cutoff - pd.Timedelta(days=self.max_history_days - 1)
        hist = history.loc[history["timestamp"] >= start, list(HISTORY_COLUMNS)].copy()
        raw = self._predict(hist, horizon)
        return finalize_forecast(raw, cutoff, horizon, sorted(hist["series_id"].unique()))


def finalize_forecast(
    raw: pd.DataFrame, cutoff: pd.Timestamp, horizon: int, expected_series: list[str]
) -> pd.DataFrame:
    """Check shape and values, sort quantiles, add cutoff and target dates."""
    missing_cols = {"series_id", "horizon", *QUANTILE_COLUMNS} - set(raw.columns)
    if missing_cols:
        raise ValueError(f"model output lacks columns {sorted(missing_cols)}")
    out = raw[["series_id", "horizon", *QUANTILE_COLUMNS]].copy()
    out["horizon"] = out["horizon"].astype(int)
    expected = {(s, h) for s in expected_series for h in range(1, horizon + 1)}
    got = set(zip(out["series_id"], out["horizon"], strict=True))
    if got != expected or len(out) != len(expected):
        raise ValueError(
            f"model returned {len(out)} rows; expected one per series and horizon ({len(expected)})"
        )
    values = out[list(QUANTILE_COLUMNS)].to_numpy(dtype="float64")
    if not np.isfinite(values).all():
        raise ValueError("model returned non-finite quantiles")
    # Sorting removes quantile crossing without changing the set of predicted values.
    out[list(QUANTILE_COLUMNS)] = np.sort(values, axis=1)
    out["cutoff"] = pd.Timestamp(cutoff)
    out["target_date"] = out["cutoff"] + pd.to_timedelta(out["horizon"], unit="D")
    return out[list(FORECAST_COLUMNS)].sort_values(["series_id", "horizon"]).reset_index(drop=True)


def intervals_to_quantiles(df: pd.DataFrame, model_col: str) -> pd.DataFrame:
    """Turn ``<model>``, ``<model>-lo-L``, ``<model>-hi-L`` columns into the 9 quantile columns."""
    out = pd.DataFrame({"series_id": df["unique_id"].to_numpy()})
    out["q0.5"] = df[model_col].to_numpy()
    for level in LEVELS:
        lo_q = round((1 - level / 100) / 2, 1)
        hi_q = round((1 + level / 100) / 2, 1)
        out[f"q{lo_q:.1f}"] = df[f"{model_col}-lo-{level}"].to_numpy()
        out[f"q{hi_q:.1f}"] = df[f"{model_col}-hi-{level}"].to_numpy()
    return out


def add_horizon(df: pd.DataFrame) -> pd.DataFrame:
    """Number rows 1..H within each series, in the order the model returned them."""
    df = df.copy()
    df["horizon"] = df.groupby("series_id").cumcount() + 1
    return df


def to_nixtla(history: pd.DataFrame) -> pd.DataFrame:
    """Nixtla libraries expect ``unique_id, ds, y``."""
    return history.rename(columns={"series_id": "unique_id", "timestamp": "ds", "value": "y"})


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hf_weights(repo: str, revision: str, filename: str = "model.safetensors") -> tuple[str, str]:
    """Download pinned weights (cached) and return ``(local_path, sha256)``."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(repo_id=repo, filename=filename, revision=revision)
    return path, file_sha256(path)
