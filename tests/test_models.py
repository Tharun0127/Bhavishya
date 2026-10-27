"""Model interface, leakage guard and baseline wrappers.

Test histories here are deterministic patterns chosen by the test (a weekly cycle), used only
to check plumbing. They are never presented as data or results.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bhavishya.models.base import (
    FORECAST_COLUMNS,
    QUANTILE_COLUMNS,
    Forecaster,
    LeakageError,
    ModelInfo,
    check_no_leakage,
    finalize_forecast,
    truncate_history,
)

WEEK = [10.0, 12.0, 14.0, 13.0, 11.0, 9.0, 8.0]


def weekly(n_weeks: int = 30, offset: float = 0.0) -> list[float]:
    return [v + offset for v in WEEK * n_weeks]


@pytest.fixture
def history(make_history) -> pd.DataFrame:
    return make_history({"a": weekly(), "b": weekly(offset=100.0)})


class SpyModel(Forecaster):
    """Records the newest timestamp it was shown and predicts a flat line."""

    seen_max: pd.Timestamp | None = None

    def info(self) -> ModelInfo:
        return ModelInfo("spy", "baseline", "0")

    def _predict(self, history: pd.DataFrame, horizon: int) -> pd.DataFrame:
        SpyModel.seen_max = history["timestamp"].max()
        rows = []
        for sid, part in history.groupby("series_id"):
            last = part["value"].iloc[-1]
            for h in range(1, horizon + 1):
                rows.append({"series_id": sid, "horizon": h, **{c: last for c in QUANTILE_COLUMNS}})
        return pd.DataFrame(rows)


def test_forecaster_rejects_history_after_cutoff(history):
    cutoff = history["timestamp"].max() - pd.Timedelta(days=5)
    with pytest.raises(LeakageError):
        SpyModel().forecast(history, cutoff, 7)


def test_truncate_then_forecast_never_shows_future(history):
    cutoff = history["timestamp"].max() - pd.Timedelta(days=5)
    out = SpyModel().forecast(truncate_history(history, cutoff), cutoff, 7)
    assert SpyModel.seen_max == cutoff
    assert (out["target_date"] > cutoff).all()
    assert out["target_date"].min() == cutoff + pd.Timedelta(days=1)
    assert tuple(out.columns) == FORECAST_COLUMNS


def test_check_no_leakage_allows_equal_cutoff(history):
    check_no_leakage(history, history["timestamp"].max())


def test_finalize_sorts_crossing_quantiles_and_checks_shape():
    raw = pd.DataFrame({"series_id": ["a", "a"], "horizon": [1, 2],
                        **{c: [9 - i, 9 - i] for i, c in enumerate(QUANTILE_COLUMNS)}})
    out = finalize_forecast(raw, pd.Timestamp("2026-01-31"), 2, ["a"])
    assert (np.diff(out[list(QUANTILE_COLUMNS)].to_numpy(), axis=1) >= 0).all()
    with pytest.raises(ValueError, match="expected one per series"):
        finalize_forecast(raw.iloc[:1], pd.Timestamp("2026-01-31"), 2, ["a"])
    bad = raw.copy()
    bad.loc[0, "q0.5"] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        finalize_forecast(bad, pd.Timestamp("2026-01-31"), 2, ["a"])


@pytest.mark.parametrize("name", ["seasonal_naive", "auto_ets", "auto_arima", "lightgbm"])
def test_baselines_contract(name, history):
    from bhavishya.models.registry import MODELS

    model = MODELS[name].load()
    cutoff = history["timestamp"].max()
    out = model.forecast(history, cutoff, 28)
    assert len(out) == 2 * 28
    assert set(out["series_id"]) == {"a", "b"}
    q = out[list(QUANTILE_COLUMNS)].to_numpy()
    assert np.isfinite(q).all() and (np.diff(q, axis=1) >= 0).all()
    info = model.info()
    assert info.name == name and info.version


def test_seasonal_naive_repeats_last_week(history):
    from bhavishya.models.baselines import SeasonalNaive

    cutoff = history["timestamp"].max()
    out = SeasonalNaive().forecast(history, cutoff, 14)
    a = out[out["series_id"] == "a"].sort_values("horizon")
    last_week = history[history["series_id"] == "a"]["value"].iloc[-7:].tolist()
    assert a["q0.5"].tolist() == pytest.approx(last_week * 2)


def test_runner_inputs_are_truncated(tmp_path, history):
    """The arena writes model inputs from an as-of view and truncates them at the cutoff."""
    from bhavishya.arena.daily import regularise

    cutoff = pd.Timestamp("2026-03-01")
    gappy = truncate_history(history, cutoff).drop(index=[3, 4])
    regular, filled = regularise(gappy, cutoff)
    assert filled == 2
    assert regular["timestamp"].max() == cutoff
    assert regular.groupby("series_id").size().nunique() == 1


@pytest.mark.slow
@pytest.mark.parametrize("name", ["chronos2", "timesfm2_5"])
def test_foundation_models_contract(name, history):
    from bhavishya.models.registry import MODELS

    model = MODELS[name].load()
    out = model.forecast(history, history["timestamp"].max(), 28)
    assert len(out) == 56
    info = model.info()
    assert info.weights_revision and info.weights_sha256 and len(info.weights_sha256) == 64
