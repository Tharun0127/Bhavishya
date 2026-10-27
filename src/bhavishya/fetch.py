"""Download, snapshot, parse and validate files from one source."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from bhavishya.contracts import ContractError, empty_tidy
from bhavishya.http import PoliteClient
from bhavishya.sources.base import FileRef, Source
from bhavishya.store import VintageStore, sha256_bytes

log = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """What happened when fetching one source."""

    source: str
    data: pd.DataFrame
    ok_files: int = 0
    missing_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    contract_errors: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not self.errors and not self.contract_errors


def today_ist() -> pd.Timestamp:
    """Today's date in India. All arena dates are IST calendar dates."""
    return pd.Timestamp.now(tz="Asia/Kolkata").tz_localize(None).normalize()


def fetch_source(
    source: Source,
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    client: PoliteClient | None = None,
    store: VintageStore | None = None,
    backfill: bool = False,
    skip_known: bool = True,
) -> FetchResult:
    """Fetch every file of ``source`` covering ``[start, end]``.

    Live fetches stamp rows with today's date as vintage: that is when we saw the data.
    Backfills stamp rows with the source's own publication date, because that is when the data
    existed publicly, and keep the raw files out of the published snapshot folder.
    """
    client = client or PoliteClient()
    result = FetchResult(source=source.name, data=empty_tidy())
    try:
        refs = source.list_files(client, start, end)
    except Exception as exc:  # network or listing format failure: whole source is down today
        result.errors.append(f"listing failed: {exc!r}")
        return result
    known = store.known_hashes(source.name) if (store and skip_known) else set()
    frames = []
    for ref in refs:
        frame = _fetch_one(source, ref, client, store, backfill, known, result)
        if frame is not None:
            frames.append(frame)
    if frames:
        result.data = pd.concat(frames, ignore_index=True)
    return result


def _fetch_one(
    source: Source,
    ref: FileRef,
    client: PoliteClient,
    store: VintageStore | None,
    backfill: bool,
    known: set[str],
    result: FetchResult,
) -> pd.DataFrame | None:
    fetched_at = pd.Timestamp.now(tz="UTC")
    vintage = (ref.published or today_ist()) if backfill else today_ist()
    log_row: dict[str, object] = {
        "source": source.name,
        "vintage_date": f"{vintage:%Y-%m-%d}",
        "fetched_at": fetched_at.isoformat(),
        "url": ref.url,
        "filename": ref.filename,
    }
    try:
        content = source.download(client, ref)
    except Exception as exc:
        result.errors.append(f"{ref.filename}: download failed: {exc!r}")
        return None
    if content is None:
        result.missing_files.append(ref.filename)
        return None
    digest = sha256_bytes(content)
    if digest in known:
        return None  # identical bytes already stored: not a new vintage
    try:
        frame = source.parse(content, ref, vintage)
        source.contract.validate(frame)
    except ContractError as exc:
        result.contract_errors.append(f"{ref.filename}: {exc}")
        frame = None
    except Exception as exc:
        result.contract_errors.append(f"{ref.filename}: parse failed: {exc!r}")
        frame = None
    if store is not None:
        store.save_raw(source.name, vintage, ref.filename, content, backfill)
        status = "ok" if frame is not None else "rejected"
        store.log_fetch(
            {
                **log_row,
                "sha256": digest,
                "n_bytes": len(content),
                "n_rows": 0 if frame is None else len(frame),
                "status": status,
            }
        )
        if frame is not None:
            store.save_observations(frame)
    if frame is not None:
        result.ok_files += 1
    return frame
