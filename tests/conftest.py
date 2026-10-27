from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def daily_history(series: dict[str, list[float]], start: str = "2026-01-01") -> pd.DataFrame:
    """Small tidy history for model and scoring tests. Values are chosen by the test, not simulated."""
    rows = []
    for sid, values in series.items():
        for i, v in enumerate(values):
            rows.append((sid, pd.Timestamp(start) + pd.Timedelta(days=i), float(v)))
    return pd.DataFrame(rows, columns=["series_id", "timestamp", "value"])


@pytest.fixture
def make_history():
    return daily_history
