"""The interface every data source implements."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from bhavishya.contracts import Contract
from bhavishya.http import PoliteClient


@dataclass(frozen=True)
class FileRef:
    """One downloadable file (or API response) from a source.

    ``published`` is the date the source says the file was released, when it says so.
    It becomes the vintage date of the rows inside, because that is when the data existed publicly.
    """

    url: str
    filename: str
    obs_date: pd.Timestamp | None = None
    published: pd.Timestamp | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceInfo:
    """Human-facing facts about a source, used in docs and on the site."""

    name: str
    title: str
    publisher: str
    homepage: str
    licence: str
    attribution: str
    release_lag: str


class Source(ABC):
    """A data source: knows how to list its files and parse one file into tidy rows."""

    info: SourceInfo
    contract: Contract

    @property
    def name(self) -> str:
        return self.info.name

    @abstractmethod
    def list_files(self, client: PoliteClient, start: pd.Timestamp, end: pd.Timestamp) -> list[FileRef]:
        """List files whose observations fall in ``[start, end]`` (dates, inclusive)."""

    @abstractmethod
    def parse(self, content: bytes, ref: FileRef, vintage_date: pd.Timestamp) -> pd.DataFrame:
        """Turn the raw bytes of one file into a tidy frame."""

    def download(self, client: PoliteClient, ref: FileRef) -> bytes | None:
        """Download one file. Returns ``None`` if the source says it does not exist (404)."""
        resp = client.get(ref.url, params=ref.params or None)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content


def slugify(text: str) -> str:
    """Lower-case ASCII slug: ``"J&K(UT) & Ladakh"`` -> ``"j_k_ut_ladakh"``."""
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
