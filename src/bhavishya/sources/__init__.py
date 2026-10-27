"""Registry of data sources."""

from __future__ import annotations

from bhavishya.sources.base import FileRef, Source, SourceInfo
from bhavishya.sources.cpcb_aqi import CpcbAqi
from bhavishya.sources.grid_india import GridIndia
from bhavishya.sources.open_meteo import OpenMeteo

SOURCES: dict[str, Source] = {s.name: s for s in (GridIndia(), CpcbAqi(), OpenMeteo())}

#: Sources whose series can be arena targets. Open-Meteo is covariates only (docs/DECISIONS.md D3).
TARGET_SOURCES: tuple[str, ...] = ("grid_india", "cpcb_aqi")


def get_source(name: str) -> Source:
    """Look up a source by name, with a helpful error."""
    try:
        return SOURCES[name]
    except KeyError:
        raise KeyError(f"unknown source {name!r}; choose from {sorted(SOURCES)}") from None


__all__ = ["SOURCES", "TARGET_SOURCES", "FileRef", "Source", "SourceInfo", "get_source"]
