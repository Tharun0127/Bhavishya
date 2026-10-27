"""Known-answer tests for every metric, the skill aggregation and the hash manifest."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from bhavishya.arena import leaderboard as lb
from bhavishya.arena.daily import mase_scales
from bhavishya.arena.hashing import append_manifest, sha256_file, verify_manifest
from bhavishya.arena.scoring import covered, crps_from_quantiles, pinball, score_frame
from bhavishya.models.base import QUANTILE_COLUMNS, QUANTILES


def test_pinball_known_values():
    y = np.array([10.0])
    q = np.array([[8.0, 12.0]])
    tau = np.array([0.1, 0.9])
    # under-forecast by 2 at tau=0.1 -> 0.2 ; over-forecast by 2 at tau=0.9 -> 0.2
    assert pinball(y, q, tau).ravel().tolist() == pytest.approx([0.2, 0.2])


def test_crps_of_perfect_point_forecast_is_zero():
    y = np.array([5.0])
    q = np.full((1, 9), 5.0)
    assert crps_from_quantiles(y, q)[0] == 0.0


def test_crps_point_forecast_equals_absolute_error():
    # For a degenerate forecast, mean over symmetric levels of 2*pinball equals |y - x|.
    y = np.array([3.0])
    q = np.full((1, 9), 1.0)
    assert crps_from_quantiles(y, q)[0] == pytest.approx(2.0)


def test_crps_hand_computed():
    y = np.array([0.0])
    q = np.array([np.arange(-4.0, 5.0)])  # quantiles -4..4 at levels 0.1..0.9
    tau = np.asarray(QUANTILES)
    expected = np.mean([2 * max(t * (0 - x), (t - 1) * (0 - x)) for t, x in zip(tau, q[0], strict=True)])
    assert crps_from_quantiles(y, q)[0] == pytest.approx(expected)
    # by hand: losses 0.4, 0.6, 0.6, 0.4, 0, 0.4, 0.6, 0.6, 0.4 sum to 4.0, so CRPS = 2 * 4 / 9
    assert expected == pytest.approx(8 / 9)


def test_coverage():
    assert covered(np.array([1.0, 5.0, 9.0]), np.array([2.0, 2, 2]), np.array([8.0, 8, 8])).tolist() == [
        False,
        True,
        False,
    ]


def test_mase_scale_known_value():
    hist = pd.DataFrame(
        {"series_id": "a", "timestamp": pd.date_range("2026-01-01", periods=14), "value": list(range(14))}
    )
    # every 7-day difference is exactly 7
    assert mase_scales(hist)["mase_scale"].iloc[0] == 7.0


def _forecast_row(model: str, sid: str, run: str, h: int, median: float, width: float) -> dict:
    qs = {c: median + width * (q - 0.5) for c, q in zip(QUANTILE_COLUMNS, QUANTILES, strict=True)}
    cutoff = pd.Timestamp(run) - pd.Timedelta(days=1)
    return {
        "model": model,
        "source": "s",
        "series_id": sid,
        "cutoff": cutoff,
        "horizon": h,
        "target_date": cutoff + pd.Timedelta(days=h),
        "run_date": pd.Timestamp(run),
        **qs,
    }


def test_score_frame_and_prospective_flag():
    fc = pd.DataFrame([_forecast_row("m", "a", "2026-01-10", 1, 10.0, 0.0)])
    actuals = pd.DataFrame(
        {
            "series_id": ["a"],
            "timestamp": [pd.Timestamp("2026-01-10")],
            "value": [13.0],
            "vintage_date": [pd.Timestamp("2026-01-11")],
        }
    )
    scales = pd.DataFrame({"run_date": [pd.Timestamp("2026-01-10")], "series_id": ["a"], "mase_scale": [2.0]})
    s = score_frame(fc, actuals, scales).iloc[0]
    assert s["abs_error"] == 3.0 and s["mase"] == 1.5 and s["crps"] == pytest.approx(3.0)
    assert s["scaled_crps"] == pytest.approx(1.5) and not s["covered_80"] and s["prospective"]
    # an actual published on the run date itself is not prospective
    early = actuals.assign(vintage_date=pd.Timestamp("2026-01-10"))
    assert not score_frame(fc, early, scales).iloc[0]["prospective"]


def _scores(ratio_by_series: dict[str, float], days: int = 5) -> pd.DataFrame:
    rows = []
    for d in range(days):
        run = pd.Timestamp("2026-01-01") + pd.Timedelta(days=d)
        for sid, ratio in ratio_by_series.items():
            for model, val in (("seasonal_naive", 1.0), ("m", ratio)):
                rows.append(
                    {
                        "model": model,
                        "series_id": sid,
                        "run_date": run,
                        "horizon": 1,
                        "scaled_crps": val,
                        "mase": val,
                        "covered_80": True,
                    }
                )
    return pd.DataFrame(rows)


def test_relative_skill_is_geometric_mean_of_series_ratios():
    s = lb.relative_skill(_scores({"a": 0.5, "b": 2.0}), "m", "scaled_crps", n_boot=50)
    assert s.value == pytest.approx(1.0)  # sqrt(0.5 * 2.0)
    s = lb.relative_skill(_scores({"a": 0.5, "b": 0.5}), "m", "scaled_crps", n_boot=50)
    assert s.value == pytest.approx(0.5)
    assert s.lo == pytest.approx(0.5) and s.hi == pytest.approx(0.5)
    assert s.n_series == 2


def test_leaderboard_withholds_rank_below_minimums():
    board = lb.leaderboard(_scores({"a": 0.5}), {"m": 3, "seasonal_naive": 3}, n_boot=20)
    assert not board["eligible"].any()
    assert board["rank"].isna().all()


def test_manifest_detects_tampering(tmp_path):
    f = tmp_path / "forecasts" / "2026-01-01" / "forecasts.parquet"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"original")
    append_manifest(
        tmp_path,
        {
            "run_date": "2026-01-01",
            "path": "forecasts/2026-01-01/forecasts.parquet",
            "sha256": sha256_file(f),
            "n_rows": 1,
            "models": "m",
            "created_at_utc": "x",
        },
    )
    assert verify_manifest(tmp_path) == []
    f.write_bytes(b"edited later")
    assert verify_manifest(tmp_path) == ["forecasts/2026-01-01/forecasts.parquet: hash mismatch"]
    with pytest.raises(FileExistsError):
        append_manifest(
            tmp_path,
            {
                "run_date": "2026-01-01",
                "path": "forecasts/2026-01-01/forecasts.parquet",
                "sha256": "x",
                "n_rows": 1,
                "models": "m",
                "created_at_utc": "x",
            },
        )


def test_sha256_known_answer(tmp_path):
    f = tmp_path / "x"
    f.write_bytes(b"abc")
    assert sha256_file(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
