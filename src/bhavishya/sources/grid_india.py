"""Grid-India (formerly POSOCO) daily Power Supply Position (PSP) reports.

Each morning around 09:30 IST the National Load Despatch Centre publishes a report for the
previous day. We read the XLS version (the PDF has the same numbers) and extract:

* ``grid_india/energy_met/<state>``: energy met per state, million units (MU, = GWh).
* ``grid_india/max_demand/<state>``: maximum demand met during the day per state, MW.
* ``grid_india/energy_met/all_india`` and ``grid_india/max_demand/all_india``.
"""

from __future__ import annotations

import io
import re

import pandas as pd

from bhavishya.contracts import Contract, UnitRange, make_tidy
from bhavishya.http import PoliteClient
from bhavishya.sources.base import FileRef, Source, SourceInfo, slugify

LIST_URL = "https://webapi.grid-india.in/api/v1/file"
FILE_BASE = "https://webcdn.grid-india.in/"

# Rows in section C that are not states. They are excluded from series to keep ids meaningful.
_NON_STATE = re.compile(r"^(bulk consumer|railways|total|region)", re.IGNORECASE)
_TITLE_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{2})")


def _financial_year(ts: pd.Timestamp) -> str:
    start = ts.year if ts.month >= 4 else ts.year - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _cell(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()  # type: ignore[call-overload]


def _to_float(value: object) -> float | None:
    try:
        out = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    return None if pd.isna(out) else out


class GridIndia(Source):
    info = SourceInfo(
        name="grid_india",
        title="Grid-India daily Power Supply Position report",
        publisher="Grid Controller of India Ltd (Grid-India), National Load Despatch Centre",
        homepage="https://grid-india.in/en/reports/daily-psp-report",
        licence="Public report on a Government of India company website. See DATA_SOURCES.md.",
        attribution="Source: Grid Controller of India Ltd (Grid-India), Daily PSP Report.",
        release_lag="Report for day D is published on day D+1, usually before 10:00 IST.",
    )
    contract = Contract(
        source="grid_india",
        frequency="D",
        units={"MU": UnitRange(0.0, 10_000.0), "MW": UnitRange(0.0, 400_000.0)},
        max_staleness_days=3,
        min_rows_per_file=20,
        series_prefix="grid_india/",
    )

    def list_files(self, client: PoliteClient, start: pd.Timestamp, end: pd.Timestamp) -> list[FileRef]:
        refs: dict[pd.Timestamp, FileRef] = {}
        for month in pd.period_range(start, end, freq="M"):
            first_day = month.to_timestamp()
            payload = {
                "_source": "GRDW",
                "_type": "DAILY_PSP_REPORT",
                "_fileDate": _financial_year(first_day),
                "_month": f"{month.month:02d}",
            }
            resp = client.post(LIST_URL, json=payload)
            resp.raise_for_status()
            for item in resp.json().get("retData") or []:
                ref = self._ref_from_listing(item)
                if ref is None or ref.obs_date is None or not (start <= ref.obs_date <= end):
                    continue
                # A re-upload for the same day replaces the earlier one in the listing view,
                # but both are kept as separate vintages if we fetched both.
                prev = refs.get(ref.obs_date)
                if prev is None or _release_key(ref) >= _release_key(prev):
                    refs[ref.obs_date] = ref
        return [refs[k] for k in sorted(refs)]

    @staticmethod
    def _ref_from_listing(item: dict[str, object]) -> FileRef | None:
        path = str(item.get("FilePath") or "")
        if not path.lower().endswith((".xls", ".xlsx")):
            return None
        match = _TITLE_DATE.search(str(item.get("Title_") or ""))
        if not match:
            return None
        dd, mm, yy = match.groups()
        obs_date = pd.Timestamp(year=2000 + int(yy), month=int(mm), day=int(dd))
        created = pd.to_datetime(str(item.get("CreatedOn") or ""), format="%d-%m-%Y %H:%M", errors="coerce")
        published = None if pd.isna(created) else pd.Timestamp(created).normalize()
        return FileRef(
            url=FILE_BASE + path, filename=path.rsplit("/", 1)[-1], obs_date=obs_date, published=published
        )

    def parse(self, content: bytes, ref: FileRef, vintage_date: pd.Timestamp) -> pd.DataFrame:
        if ref.obs_date is None:
            raise ValueError("Grid-India file without an observation date")
        sheet = pd.read_excel(io.BytesIO(content), sheet_name=0, header=None)
        rows = _parse_all_india(sheet, ref.obs_date) + _parse_states(sheet, ref.obs_date)
        return make_tidy(rows, self.name, vintage_date)


def _release_key(ref: FileRef) -> pd.Timestamp:
    """Order re-uploads of the same day by publication date, falling back to the observation date."""
    return ref.published or ref.obs_date or pd.Timestamp.min


def _find_row(sheet: pd.DataFrame, pattern: str, col: int = 0, start: int = 0) -> int | None:
    regex = re.compile(pattern, re.IGNORECASE)
    for i in range(start, len(sheet)):
        if regex.search(_cell(sheet.iat[i, col])):
            return i
    return None


def _parse_all_india(
    sheet: pd.DataFrame, obs_date: pd.Timestamp
) -> list[tuple[str, pd.Timestamp, float, str]]:
    """Section A has one column per region and a TOTAL column for all of India."""
    header = None
    for i in range(min(15, len(sheet))):
        labels = [_cell(v).upper() for v in sheet.iloc[i].tolist()]
        if "NR" in labels and "TOTAL" in labels:
            header, total_col = i, labels.index("TOTAL")
            break
    if header is None:
        raise ValueError("section A header (NR ... TOTAL) not found")
    out: list[tuple[str, pd.Timestamp, float, str]] = []
    targets = {
        r"^Energy Met": ("energy_met", "MU"),
        r"^Maximum Demand Met During the Day": ("max_demand", "MW"),
    }
    for pattern, (metric, unit) in targets.items():
        row = _find_row(sheet, pattern, start=header)
        value = None if row is None else _to_float(sheet.iat[row, total_col])
        if value is None:
            raise ValueError(f"all-India {metric} not found")
        out.append((f"grid_india/{metric}/all_india", obs_date, value, unit))
    return out


def _parse_states(sheet: pd.DataFrame, obs_date: pd.Timestamp) -> list[tuple[str, pd.Timestamp, float, str]]:
    """Section C: one row per state with max demand met (MW) and energy met (MU)."""
    header = None
    for i in range(len(sheet)):
        labels = [_cell(v) for v in sheet.iloc[i].tolist()]
        if any(s.startswith("Max.Demand") for s in labels) and any(
            s.startswith("Energy Met") for s in labels
        ):
            header = i
            demand_col = next(j for j, s in enumerate(labels) if s.startswith("Max.Demand"))
            energy_col = next(j for j, s in enumerate(labels) if s.startswith("Energy Met"))
            break
    if header is None:
        raise ValueError("section C header (Max.Demand, Energy Met) not found")
    out: list[tuple[str, pd.Timestamp, float, str]] = []
    for i in range(header + 2, len(sheet)):
        if _cell(sheet.iat[i, 0]).startswith("D."):
            break  # next section
        state = _cell(sheet.iat[i, 1])
        if not state or _NON_STATE.match(state):
            continue
        slug = slugify(state)
        demand, energy = _to_float(sheet.iat[i, demand_col]), _to_float(sheet.iat[i, energy_col])
        if energy is not None:
            out.append((f"grid_india/energy_met/{slug}", obs_date, energy, "MU"))
        if demand is not None:
            out.append((f"grid_india/max_demand/{slug}", obs_date, demand, "MW"))
    if len(out) < 20:
        raise ValueError(f"only {len(out)} state values parsed; layout probably changed")
    return out
