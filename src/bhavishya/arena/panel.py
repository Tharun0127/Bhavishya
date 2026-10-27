"""The fixed launch panel of target series, and the rules that chose it.

The rules are written down in config/panel.yaml before any forecast was made. They use only
data with vintage on or before the freeze date, so they cannot depend on future outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

# Largest urban agglomerations in India by the 2011 Census (a list fixed long before the
# arena), in rank order. Used only to rank CPCB cities; coverage decides which are kept.
CENSUS_2011_TOP_CITIES: tuple[str, ...] = (
    "mumbai",
    "delhi",
    "kolkata",
    "chennai",
    "bengaluru",
    "hyderabad",
    "ahmedabad",
    "pune",
    "surat",
    "jaipur",
    "kanpur",
    "lucknow",
    "nagpur",
    "ghaziabad",
    "indore",
    "coimbatore",
    "kochi",
    "patna",
    "kozhikode",
    "bhopal",
    "thrissur",
    "vadodara",
    "agra",
    "visakhapatnam",
    "malappuram",
    "thiruvananthapuram",
    "kannur",
    "ludhiana",
    "nashik",
    "vijayawada",
)

N_STATES = 15
N_CITIES = 20
LOOKBACK_DAYS = 365
MIN_COVERAGE = 0.85


@dataclass(frozen=True)
class Panel:
    version: str
    frozen_on: pd.Timestamp
    series: tuple[str, ...]

    def for_source(self, source: str) -> list[str]:
        return [s for s in self.series if s.startswith(source + "/")]

    @property
    def sources(self) -> list[str]:
        return sorted({s.split("/", 1)[0] for s in self.series})


def load_panel(path: str | Path = "config/panel.yaml") -> Panel:
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return Panel(str(cfg["version"]), pd.Timestamp(cfg["frozen_on"]), tuple(cfg["series"]))


def coverage(obs: pd.DataFrame, end: pd.Timestamp, days: int = LOOKBACK_DAYS) -> pd.Series:
    """Share of the ``days`` days ending at ``end`` that have a value, per series."""
    start = end - pd.Timedelta(days=days - 1)
    window = obs[(obs["timestamp"] >= start) & (obs["timestamp"] <= end)]
    return window.groupby("series_id")["timestamp"].nunique() / days


def select_panel(obs: pd.DataFrame, frozen_on: pd.Timestamp) -> tuple[list[str], pd.DataFrame]:
    """Apply the written selection rules to data as it existed on ``frozen_on``.

    ``obs`` must already be an as-of view at ``frozen_on`` (no later vintages).
    Returns the chosen series and a table of the statistics used, for the record.
    """
    if (obs["vintage_date"] > frozen_on).any():
        raise ValueError("selection data contains vintages after the freeze date")
    end = obs["timestamp"].max()
    cov = coverage(obs, end)
    stats = pd.DataFrame({"coverage": cov})
    stats["mean_value"] = (
        obs[obs["timestamp"] > end - pd.Timedelta(days=LOOKBACK_DAYS)].groupby("series_id")["value"].mean()
    )
    chosen: list[str] = []

    # Grid-India: national totals, then the largest states by mean energy met.
    for sid in ("grid_india/energy_met/all_india", "grid_india/max_demand/all_india"):
        if cov.get(sid, 0) >= MIN_COVERAGE:
            chosen.append(sid)
    states = stats[
        stats.index.str.startswith("grid_india/energy_met/")
        & ~stats.index.str.endswith("/all_india")
        & (stats["coverage"] >= MIN_COVERAGE)
    ].sort_values("mean_value", ascending=False)
    chosen += list(states.index[:N_STATES])

    # CPCB: the largest cities (Census 2011 order) with enough bulletin coverage.
    cities = [f"cpcb_aqi/aqi/{c}" for c in CENSUS_2011_TOP_CITIES]
    chosen += [c for c in cities if cov.get(c, 0) >= MIN_COVERAGE][:N_CITIES]
    stats["selected"] = stats.index.isin(chosen)
    return chosen, stats.loc[stats.index.isin(chosen) | stats.index.isin(cities)]
