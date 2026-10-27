"""Open-Meteo daily weather for Indian cities, used as covariates.

Open-Meteo values are model output (reanalysis and forecast blends), not observations,
and they can be revised. That is why they are covariates here, never arena targets.
"""

from __future__ import annotations

import json

import pandas as pd

from bhavishya.contracts import Contract, UnitRange, make_tidy
from bhavishya.http import PoliteClient
from bhavishya.sources.base import FileRef, Source, SourceInfo

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

#: City centres. Coordinates are rounded; Open-Meteo snaps to its own grid anyway.
CITIES: dict[str, tuple[float, float]] = {
    "delhi": (28.61, 77.21),
    "mumbai": (19.08, 72.88),
    "kolkata": (22.57, 88.36),
    "chennai": (13.08, 80.27),
    "bengaluru": (12.97, 77.59),
    "hyderabad": (17.39, 78.49),
    "ahmedabad": (23.02, 72.57),
    "pune": (18.52, 73.86),
    "lucknow": (26.85, 80.95),
    "jaipur": (26.91, 75.79),
    "patna": (25.59, 85.14),
    "chandigarh": (30.73, 76.78),
}
VARIABLES: dict[str, str] = {
    "temperature_2m_max": "degC",
    "temperature_2m_mean": "degC",
    "precipitation_sum": "mm",
}
# The archive endpoint lags real time by several days. Recent days come from the forecast endpoint.
ARCHIVE_LAG_DAYS = 6


class OpenMeteo(Source):
    info = SourceInfo(
        name="open_meteo",
        title="Open-Meteo daily weather (covariates)",
        publisher="Open-Meteo.com",
        homepage="https://open-meteo.com/",
        licence="CC BY 4.0 (data). Free API for non-commercial use; see open-meteo.com/en/terms.",
        attribution="Weather data by Open-Meteo.com (CC BY 4.0).",
        release_lag="Archive lags about 5 days; recent days come from the forecast API.",
    )
    contract = Contract(
        source="open_meteo",
        frequency="D",
        units={"degC": UnitRange(-40.0, 55.0), "mm": UnitRange(0.0, 1500.0)},
        max_staleness_days=2,
        min_rows_per_file=1,
        series_prefix="open_meteo/",
    )

    def list_files(self, client: PoliteClient, start: pd.Timestamp, end: pd.Timestamp) -> list[FileRef]:
        today = pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize()
        split = today - pd.Timedelta(days=ARCHIVE_LAG_DAYS)
        refs: list[FileRef] = []
        for city, (lat, lon) in CITIES.items():
            base = {
                "latitude": lat,
                "longitude": lon,
                "daily": ",".join(VARIABLES),
                "timezone": "Asia/Kolkata",
            }
            if start <= split:
                params = {**base, "start_date": f"{start:%Y-%m-%d}", "end_date": f"{min(end, split):%Y-%m-%d}"}
                refs.append(FileRef(ARCHIVE_URL, f"{city}_archive_{start:%Y%m%d}_{min(end, split):%Y%m%d}.json",
                                    params=params))
            if end > split:
                recent_start = max(start, split + pd.Timedelta(days=1))
                params = {**base, "start_date": f"{recent_start:%Y-%m-%d}", "end_date": f"{min(end, today):%Y-%m-%d}"}
                refs.append(FileRef(FORECAST_URL, f"{city}_recent_{recent_start:%Y%m%d}_{end:%Y%m%d}.json",
                                    params=params))
        return refs

    def parse(self, content: bytes, ref: FileRef, vintage_date: pd.Timestamp) -> pd.DataFrame:
        payload = json.loads(content)
        city = ref.filename.split("_", 1)[0]
        daily = payload["daily"]
        rows: list[tuple[str, pd.Timestamp, float, str]] = []
        for var, unit in VARIABLES.items():
            for day, value in zip(daily["time"], daily[var], strict=True):
                if value is not None:
                    rows.append((f"open_meteo/{var}/{city}", pd.Timestamp(day), float(value), unit))
        return make_tidy(rows, self.name, vintage_date)
