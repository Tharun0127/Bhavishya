"""PIPELINE TEST on recorded real observations: replay three past dates through the whole cycle.

This checks plumbing (as-of inputs, cutoffs, commit, hashes, scoring, site). The numbers it
produces are replays and are never benchmark results.
"""

from __future__ import annotations

import json

import pandas as pd
import yaml

from bhavishya.arena import daily
from bhavishya.arena.hashing import read_manifest, verify_manifest
from bhavishya.arena.panel import load_panel
from bhavishya.arena.scoring import score_all
from bhavishya.arena.site import build_site
from bhavishya.store import VintageStore

DATES = ["2026-09-15", "2026-09-22", "2026-10-01"]


def test_replay_three_dates(tmp_path, fixtures):
    store = VintageStore(tmp_path / "store")
    store.save_observations(pd.read_parquet(fixtures / "observations_sample.parquet"))
    series = sorted(store.observations()["series_id"].unique())
    panel_path = tmp_path / "panel.yaml"
    panel_path.write_text(yaml.safe_dump({"version": "test", "frozen_on": "2026-09-01", "series": series}))
    panel = load_panel(panel_path)

    for day in DATES:
        run_date = pd.Timestamp(day)
        path = daily.daily(
            store, panel, run_date, live=False, models=["seasonal_naive", "lightgbm"], stamp=False
        )
        assert path is not None and path.exists()
        run = json.loads((path.parent / "run.json").read_text())
        assert run["failures"] == {}
        for source, cutoff in run["cutoffs"].items():
            hist = pd.read_parquet(store.root / "inputs" / day / f"{source}.parquet")
            # Inputs end at the cutoff, and the cutoff is data that existed on the run date.
            assert hist["timestamp"].max() == pd.Timestamp(cutoff) <= run_date
            known = store.as_of(run_date, [source])
            assert pd.Timestamp(cutoff) == known[known["series_id"].isin(series)]["timestamp"].max()
        fc = pd.read_parquet(path)
        assert set(fc["model"]) == {"seasonal_naive", "lightgbm"}
        assert (fc["target_date"] > fc["cutoff"]).all()

    assert len(read_manifest(store.root)) == 3
    assert verify_manifest(store.root) == []

    scored = score_all(store)
    assert len(scored) > 0
    # Every scored actual was published after the forecast was committed.
    assert (scored["actual_vintage"] > scored["run_date"]).all()
    assert scored["covered_80"].between(0, 1).all()

    out = tmp_path / "site"
    build_site(store, panel, fixtures.parent.parent / "docs", out)
    assert (out / "index.html").exists() and (out / "status.html").exists()
    assert len(list((out / "series").glob("*.html"))) == len(series)

    # Committing the same day twice is refused: forecasts are append-only.
    try:
        daily.commit_forecasts(store, pd.Timestamp(DATES[0]), stamp=False)
    except FileExistsError:
        pass
    else:
        raise AssertionError("re-commit should be refused")
