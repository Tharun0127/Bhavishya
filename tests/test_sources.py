"""Loader tests on files recorded from the real sources (tests/fixtures)."""

from __future__ import annotations

import pandas as pd
import pytest

from bhavishya.contracts import TIDY_COLUMNS
from bhavishya.sources import get_source
from bhavishya.sources.base import FileRef, slugify
from bhavishya.sources.grid_india import GridIndia, _financial_year


def _parse(name: str, path, day: str) -> pd.DataFrame:
    src = get_source(name)
    ref = FileRef(url="u", filename=path.name, obs_date=pd.Timestamp(day))
    df = src.parse(path.read_bytes(), ref, pd.Timestamp(day))
    src.contract.validate(df)
    return df


@pytest.mark.parametrize(
    ("fixture", "day", "expected"),
    [
        (
            "grid_india_psp_2026-10-26.xls",
            "2026-10-26",
            {
                "grid_india/energy_met/all_india": 4858.27,
                "grid_india/max_demand/all_india": 227898.0,
                "grid_india/energy_met/punjab": 168.56,
                "grid_india/energy_met/delhi": 90.7,
                "grid_india/max_demand/maharashtra": 30541.0,
            },
        ),
        (
            "grid_india_psp_2025-04-30.xls",
            "2025-04-30",
            {
                "grid_india/energy_met/all_india": 5085.71,
                "grid_india/energy_met/punjab": 217.61,
                "grid_india/max_demand/tamil_nadu": 19952.0,
            },
        ),
    ],
)
def test_grid_india_known_values(fixtures, fixture, day, expected):
    df = _parse("grid_india", fixtures / fixture, day)
    values = df.set_index("series_id")["value"]
    for sid, val in expected.items():
        assert values[sid] == pytest.approx(val)
    assert (df["timestamp"] == pd.Timestamp(day)).all()
    assert tuple(df.columns) == TIDY_COLUMNS


def test_grid_india_skips_non_state_rows(fixtures):
    df = _parse("grid_india", fixtures / "grid_india_psp_2026-10-26.xls", "2026-10-26")
    assert not df["series_id"].str.contains("bulk_consumer").any()


@pytest.mark.parametrize(
    ("fixture", "day", "delhi", "mumbai", "min_cities"),
    [
        ("cpcb_aqi_2026-10-26.pdf", "2026-10-26", 174.0, 105.0, 250),
        ("cpcb_aqi_2023-01-01.pdf", "2023-01-01", 259.0, 147.0, 150),
    ],
)
def test_cpcb_known_values(fixtures, fixture, day, delhi, mumbai, min_cities):
    df = _parse("cpcb_aqi", fixtures / fixture, day)
    values = df.set_index("series_id")["value"]
    assert values["cpcb_aqi/aqi/delhi"] == delhi
    assert values["cpcb_aqi/aqi/mumbai"] == mumbai
    assert len(df) >= min_cities
    assert df["series_id"].is_unique


def test_open_meteo_parse(fixtures):
    path = fixtures / "open_meteo_delhi_recent_20261022_20261026.json"
    df = _parse("open_meteo", path, "2026-10-27")
    assert set(df["unit"]) == {"degC", "mm"}
    assert df["timestamp"].min() == pd.Timestamp("2026-10-22")
    assert df["series_id"].str.endswith("/delhi").all()


def test_grid_india_listing_parsing():
    item = {
        "FilePath": "files/grdw/2026/10/26.10.26_NLDC_PSP_247.xls",
        "Title_": "26.10.26_NLDC_PSP",
        "CreatedOn": "27-10-2026 09:41",
    }
    ref = GridIndia._ref_from_listing(item)
    assert ref is not None
    assert ref.obs_date == pd.Timestamp("2026-10-26")
    assert ref.published == pd.Timestamp("2026-10-27")
    assert GridIndia._ref_from_listing({**item, "FilePath": "x.pdf"}) is None


def test_financial_year():
    assert _financial_year(pd.Timestamp("2026-03-31")) == "2025-26"
    assert _financial_year(pd.Timestamp("2026-04-01")) == "2026-27"


def test_slugify():
    assert slugify("J&K(UT) & Ladakh") == "j_k_ut_ladakh"
    assert slugify("  Tamil Nadu ") == "tamil_nadu"


def test_corrupt_file_raises(fixtures):
    src = get_source("grid_india")
    with pytest.raises(Exception):  # noqa: B017 - any parse error is acceptable here
        src.parse(
            b"not an excel file",
            FileRef("u", "f", obs_date=pd.Timestamp("2026-10-26")),
            pd.Timestamp("2026-10-27"),
        )
