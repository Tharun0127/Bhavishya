"""Vintage store: raw snapshots plus tidy observations, keyed by the date the data existed.

Layout under ``root``::

    raw/<source>/<vintage>/<file>             raw bytes from live daily fetches (published)
    raw_backfill/<source>/<vintage>/<file>    raw bytes from history backfills (kept local)
    observations/<source>/<vintage>.parquet   tidy rows first seen in that vintage
    raw_index.csv                             one line per downloaded file, with SHA-256

Sources revise history. Storing rows per vintage lets us answer two questions exactly:
what data existed on day D (:meth:`VintageStore.as_of`), and what was the first published
value of each observation (:meth:`VintageStore.first_release`).
"""

from __future__ import annotations

import csv
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from bhavishya.contracts import TIDY_COLUMNS, empty_tidy

INDEX_FIELDS = (
    "source",
    "vintage_date",
    "fetched_at",
    "url",
    "filename",
    "sha256",
    "n_bytes",
    "n_rows",
    "status",
)


def default_root() -> Path:
    """Package users get a per-user cache. The arena points this at its data branch checkout."""
    env = os.environ.get("BHAVISHYA_DATA_DIR")
    return Path(env) if env else Path.home() / ".cache" / "bhavishya"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass
class VintageStore:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)

    # ---- raw files -------------------------------------------------------------------------------
    def raw_path(self, source: str, vintage: pd.Timestamp, filename: str, backfill: bool) -> Path:
        folder = "raw_backfill" if backfill else "raw"
        return self.root / folder / source / f"{vintage:%Y-%m-%d}" / filename

    def save_raw(
        self, source: str, vintage: pd.Timestamp, filename: str, content: bytes, backfill: bool
    ) -> str:
        path = self.raw_path(source, vintage, filename, backfill)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return sha256_bytes(content)

    def log_fetch(self, row: dict[str, object]) -> None:
        """Append one line to the raw index. Append-only, so history of fetches is never rewritten."""
        path = self.root / "raw_index.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=INDEX_FIELDS)
            if new:
                writer.writeheader()
            writer.writerow({k: row.get(k, "") for k in INDEX_FIELDS})

    def raw_index(self) -> pd.DataFrame:
        path = self.root / "raw_index.csv"
        if not path.exists():
            return pd.DataFrame(columns=list(INDEX_FIELDS))
        return pd.read_csv(path, dtype=str)

    def known_hashes(self, source: str) -> set[str]:
        idx = self.raw_index()
        return set(idx.loc[(idx["source"] == source) & (idx["status"] == "ok"), "sha256"])

    # ---- observations ----------------------------------------------------------------------------
    def save_observations(self, df: pd.DataFrame) -> None:
        """Merge rows into their (source, vintage) files. Re-saving the same rows is a no-op."""
        for (source, vintage), part in df.groupby(["source", "vintage_date"]):
            path = self.root / "observations" / str(source) / f"{pd.Timestamp(str(vintage)):%Y-%m-%d}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                part = pd.concat([pd.read_parquet(path), part], ignore_index=True)
            part = part.drop_duplicates(["series_id", "timestamp"], keep="last")
            part = part.sort_values(["series_id", "timestamp"]).reset_index(drop=True)
            part.to_parquet(path, index=False, compression="zstd")

    def observations(
        self, sources: list[str] | None = None, as_of: pd.Timestamp | None = None
    ) -> pd.DataFrame:
        """All stored rows (every vintage) with ``vintage_date <= as_of``."""
        base = self.root / "observations"
        if not base.exists():
            return empty_tidy()
        frames = []
        for src_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            if sources and src_dir.name not in sources:
                continue
            for f in sorted(src_dir.glob("*.parquet")):
                if as_of is not None and pd.Timestamp(f.stem) > as_of:
                    continue  # file name is the vintage, so we can skip without reading
                frames.append(pd.read_parquet(f))
        if not frames:
            return empty_tidy()
        return pd.concat(frames, ignore_index=True)[list(TIDY_COLUMNS)]

    def as_of(self, as_of: pd.Timestamp, sources: list[str] | None = None) -> pd.DataFrame:
        """The data as it existed on ``as_of``: latest vintage at or before that date, per observation."""
        obs = self.observations(sources, as_of)
        obs = obs.sort_values("vintage_date").drop_duplicates(["series_id", "timestamp"], keep="last")
        return obs.sort_values(["series_id", "timestamp"]).reset_index(drop=True)

    def first_release(self, sources: list[str] | None = None) -> pd.DataFrame:
        """The first published value of each observation. Scoring uses this (docs/METHODOLOGY.md)."""
        obs = self.observations(sources)
        obs = obs.sort_values("vintage_date").drop_duplicates(["series_id", "timestamp"], keep="first")
        return obs.sort_values(["series_id", "timestamp"]).reset_index(drop=True)
