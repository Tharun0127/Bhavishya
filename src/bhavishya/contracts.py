"""Data contracts.

Every fetch is checked against its source's contract before anything downstream sees it.
A contract violation means the source changed format or sent bad data, so the arena
skips that source for the day instead of forecasting from garbage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

#: Column order of every tidy frame returned by a loader.
TIDY_COLUMNS: tuple[str, ...] = ("series_id", "timestamp", "value", "unit", "source", "vintage_date")


class ContractError(ValueError):
    """Raised when a frame breaks its source's data contract."""

    def __init__(self, source: str, problems: list[str]) -> None:
        self.source = source
        self.problems = problems
        super().__init__(f"{source}: {len(problems)} contract violation(s): " + "; ".join(problems[:5]))


@dataclass(frozen=True)
class UnitRange:
    """Valid closed range of values for one unit."""

    low: float
    high: float


@dataclass(frozen=True)
class Contract:
    """Schema, units, frequency and valid ranges for one source."""

    source: str
    frequency: str  # pandas offset alias, "D" for all launch sources
    units: dict[str, UnitRange]
    #: A fetch whose newest timestamp is older than this many days is "stale".
    max_staleness_days: int
    #: Minimum rows a non-empty fetch of one file must yield. Guards against silent parse failures.
    min_rows_per_file: int = 1
    series_prefix: str = field(default="")

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return ``df`` unchanged if it satisfies the contract, else raise :class:`ContractError`."""
        problems = check_schema(df)
        if problems:
            raise ContractError(self.source, problems)
        problems += self._check_values(df)
        if problems:
            raise ContractError(self.source, problems)
        return df

    def _check_values(self, df: pd.DataFrame) -> list[str]:
        problems: list[str] = []
        if (df["source"] != self.source).any():
            problems.append("rows from another source")
        if self.series_prefix and not df["series_id"].str.startswith(self.series_prefix).all():
            problems.append(f"series_id must start with {self.series_prefix!r}")
        unknown = set(df["unit"].unique()) - set(self.units)
        if unknown:
            problems.append(f"unknown units {sorted(unknown)}")
        if df["value"].isna().any():
            problems.append(f"{int(df['value'].isna().sum())} missing values")
        for unit, rng in self.units.items():
            vals = df.loc[df["unit"] == unit, "value"]
            bad = vals[(vals < rng.low) | (vals > rng.high)]
            if len(bad):
                problems.append(f"{len(bad)} {unit} values outside [{rng.low}, {rng.high}]")
        if df.duplicated(["series_id", "timestamp", "vintage_date"]).any():
            problems.append("duplicate (series_id, timestamp, vintage_date) rows")
        # Daily data must sit on midnight. Anything else means a timezone or parsing bug.
        if self.frequency == "D" and (df["timestamp"] != df["timestamp"].dt.normalize()).any():
            problems.append("daily timestamps not at midnight")
        return problems


def check_schema(df: pd.DataFrame) -> list[str]:
    """Check column names and dtypes of a tidy frame."""
    problems: list[str] = []
    if tuple(df.columns) != TIDY_COLUMNS:
        return [f"columns {list(df.columns)} != {list(TIDY_COLUMNS)}"]
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        problems.append("timestamp is not datetime64")
    if not pd.api.types.is_datetime64_any_dtype(df["vintage_date"]):
        problems.append("vintage_date is not datetime64")
    if not pd.api.types.is_float_dtype(df["value"]):
        problems.append("value is not float")
    return problems


def empty_tidy() -> pd.DataFrame:
    """An empty frame with the tidy schema and dtypes."""
    return pd.DataFrame(
        {
            "series_id": pd.Series(dtype="string"),
            "timestamp": pd.Series(dtype="datetime64[ns]"),
            "value": pd.Series(dtype="float64"),
            "unit": pd.Series(dtype="string"),
            "source": pd.Series(dtype="string"),
            "vintage_date": pd.Series(dtype="datetime64[ns]"),
        }
    )


def make_tidy(
    rows: list[tuple[str, pd.Timestamp, float, str]], source: str, vintage_date: pd.Timestamp
) -> pd.DataFrame:
    """Build a tidy frame from ``(series_id, timestamp, value, unit)`` rows."""
    if not rows:
        return empty_tidy()
    df = pd.DataFrame(rows, columns=["series_id", "timestamp", "value", "unit"])
    df["source"] = source
    df["vintage_date"] = pd.Timestamp(vintage_date).normalize()
    df["timestamp"] = pd.to_datetime(df["timestamp"]).astype("datetime64[ns]")
    df["vintage_date"] = df["vintage_date"].astype("datetime64[ns]")
    df["value"] = df["value"].astype("float64")
    for col in ("series_id", "unit", "source"):
        df[col] = df[col].astype("string")
    return df[list(TIDY_COLUMNS)]
