"""CPCB daily Air Quality Index bulletin.

The Central Pollution Control Board publishes one PDF per day listing every city with a
continuous monitoring station. The index is the 24-hour average ending 16:00 IST that day.
We extract ``cpcb/aqi/<city>`` (unitless AQI, 0 to 500).
"""

from __future__ import annotations

import io
import re

import pandas as pd
import pdfplumber

from bhavishya.contracts import Contract, UnitRange, make_tidy
from bhavishya.http import PoliteClient
from bhavishya.sources.base import FileRef, Source, SourceInfo, slugify

# The http URL redirects to https on cpcb.gov.in. The https host for cpcb.nic.in did not
# answer from our network on 2026-10-27, so we go straight to the redirect target.
BULLETIN_URL = "https://cpcb.gov.in/upload/Downloads/AQI_Bulletin_{ymd}.pdf"
_INT = re.compile(r"^\d+$")


class CpcbAqi(Source):
    info = SourceInfo(
        name="cpcb_aqi",
        title="CPCB daily AQI bulletin",
        publisher="Central Pollution Control Board, Ministry of Environment, Forest and Climate Change",
        homepage="https://cpcb.nic.in/AQI_Bulletin.php",
        licence="Public bulletin on a Government of India website. See DATA_SOURCES.md.",
        attribution="Source: Central Pollution Control Board (CPCB), Daily AQI Bulletin.",
        release_lag="Bulletin for day D is published on the evening of day D (24h average to 16:00 IST).",
    )
    contract = Contract(
        source="cpcb_aqi",
        frequency="D",
        units={"aqi": UnitRange(0.0, 500.0)},
        max_staleness_days=3,
        min_rows_per_file=50,
        series_prefix="cpcb_aqi/",
    )

    def list_files(self, client: PoliteClient, start: pd.Timestamp, end: pd.Timestamp) -> list[FileRef]:
        # No listing API: the URL is a pure function of the date. Missing days come back as 404.
        return [
            FileRef(
                url=BULLETIN_URL.format(ymd=day.strftime("%Y%m%d")),
                filename=f"AQI_Bulletin_{day:%Y%m%d}.pdf",
                obs_date=day,
                published=day,
            )
            for day in pd.date_range(start, end, freq="D")
        ]

    def parse(self, content: bytes, ref: FileRef, vintage_date: pd.Timestamp) -> pd.DataFrame:
        if ref.obs_date is None:
            raise ValueError("CPCB bulletin without a date")
        rows: list[tuple[str, pd.Timestamp, float, str]] = []
        seen: set[str] = set()
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    for row in table:
                        parsed = _parse_row(row)
                        if parsed is None or parsed[0] in seen:
                            continue
                        seen.add(parsed[0])
                        rows.append((f"cpcb_aqi/aqi/{parsed[0]}", ref.obs_date, parsed[1], "aqi"))
        if len(rows) < self.contract.min_rows_per_file:
            raise ValueError(f"only {len(rows)} cities parsed; layout probably changed")
        return make_tidy(rows, self.name, vintage_date)


def _parse_row(row: list[str | None]) -> tuple[str, float] | None:
    """Rows look like ``['12', 'Delhi', 'Poor', '264', 'PM2.5', '38/39']``."""
    cells = [(c or "").replace("\n", " ").strip() for c in row]
    if len(cells) < 4 or not _INT.match(cells[0]) or not _INT.match(cells[3]):
        return None
    city = slugify(cells[1])
    return (city, float(cells[3])) if city else None
