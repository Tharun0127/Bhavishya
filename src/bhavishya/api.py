"""Public, high-level API of the data package."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bhavishya.contracts import ContractError
from bhavishya.fetch import fetch_source, today_ist
from bhavishya.http import PoliteClient
from bhavishya.sources import SOURCES, SourceInfo, get_source
from bhavishya.store import VintageStore, default_root


def list_sources() -> list[SourceInfo]:
    """Describe every available source."""
    return [s.info for s in SOURCES.values()]


def load(
    source: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp | None = None,
    *,
    series: list[str] | None = None,
    as_of: str | pd.Timestamp | None = None,
    cache_dir: str | Path | None = None,
    strict: bool = True,
) -> pd.DataFrame:
    """Load a tidy frame of one source between two dates (inclusive).

    Files already in the cache are not downloaded again. Every new file is checked against the
    source's data contract.

    Args:
        source: ``"grid_india"``, ``"cpcb_aqi"`` or ``"open_meteo"``.
        start: first observation date.
        end: last observation date, default today (IST).
        series: keep only these ``series_id`` values.
        as_of: return the data as it existed on this date (vintage filter). Default: latest.
        cache_dir: where to keep raw files and parsed rows. Default ``~/.cache/bhavishya``
            or ``$BHAVISHYA_DATA_DIR``.
        strict: raise :class:`~bhavishya.contracts.ContractError` if any file breaks its contract.

    Returns:
        Columns ``series_id, timestamp, value, unit, source, vintage_date``.

    Example:
        >>> import bhavishya
        >>> df = bhavishya.load("grid_india", "2026-10-01", "2026-10-07")  # doctest: +SKIP
        >>> df[df.series_id == "grid_india/energy_met/all_india"]  # doctest: +SKIP
    """
    src = get_source(source)
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize() if end is not None else today_ist()
    store = VintageStore(Path(cache_dir) if cache_dir else default_root())
    # Rows saved by a plain user load get the source's publication date as vintage (backfill mode),
    # so a user's cache and the arena's store agree on what existed when.
    result = fetch_source(src, start_ts, end_ts, client=PoliteClient(), store=store, backfill=True)
    if strict and result.contract_errors:
        raise ContractError(source, result.contract_errors)
    if result.errors and strict:
        raise RuntimeError(f"{source}: " + "; ".join(result.errors))
    as_of_ts = pd.Timestamp(as_of).normalize() if as_of is not None else pd.Timestamp.max.normalize()
    df = store.as_of(as_of_ts, [source])
    mask = (df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)
    if series:
        mask &= df["series_id"].isin(series)
    return df.loc[mask].reset_index(drop=True)


def to_wide(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot a tidy frame to one column per series, indexed by timestamp."""
    return df.pivot_table(index="timestamp", columns="series_id", values="value").sort_index()
