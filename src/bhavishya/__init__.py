"""Bhavishya: vintage-aware loaders for Indian public time series, and a live forecasting arena.

Quick start::

    import bhavishya
    df = bhavishya.load("cpcb_aqi", "2026-09-01", "2026-09-30", series=["cpcb_aqi/aqi/delhi"])
"""

from bhavishya._version import __version__
from bhavishya.api import list_sources, load, to_wide
from bhavishya.contracts import TIDY_COLUMNS, Contract, ContractError
from bhavishya.store import VintageStore

__all__ = [
    "TIDY_COLUMNS",
    "Contract",
    "ContractError",
    "VintageStore",
    "__version__",
    "list_sources",
    "load",
    "to_wide",
]
