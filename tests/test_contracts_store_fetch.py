"""Contracts, the vintage store, and the fetch pipeline (no network: a fake client serves fixtures)."""

from __future__ import annotations

import pandas as pd
import pytest

from bhavishya.contracts import ContractError, make_tidy
from bhavishya.fetch import fetch_source
from bhavishya.sources import get_source
from bhavishya.sources.base import FileRef, Source
from bhavishya.store import VintageStore

T = pd.Timestamp


def test_contract_accepts_good_frame():
    df = make_tidy([("cpcb_aqi/aqi/delhi", T("2026-10-01"), 150.0, "aqi")], "cpcb_aqi", T("2026-10-01"))
    get_source("cpcb_aqi").contract.validate(df)


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([("cpcb_aqi/aqi/delhi", T("2026-10-01"), 650.0, "aqi")], "outside"),
        ([("cpcb_aqi/aqi/delhi", T("2026-10-01"), 50.0, "ppm")], "unknown units"),
        ([("grid_india/x", T("2026-10-01"), 50.0, "aqi")], "series_id must start"),
        ([("cpcb_aqi/aqi/delhi", T("2026-10-01 05:00"), 50.0, "aqi")], "midnight"),
        ([("cpcb_aqi/aqi/delhi", T("2026-10-01"), float("nan"), "aqi")], "missing"),
    ],
)
def test_contract_rejects_bad_frames(rows, message):
    df = make_tidy(rows, "cpcb_aqi", T("2026-10-01"))
    with pytest.raises(ContractError, match=message):
        get_source("cpcb_aqi").contract.validate(df)


def test_contract_rejects_wrong_columns():
    df = make_tidy([("cpcb_aqi/aqi/delhi", T("2026-10-01"), 1.0, "aqi")], "cpcb_aqi", T("2026-10-01"))
    with pytest.raises(ContractError, match="columns"):
        get_source("cpcb_aqi").contract.validate(df.drop(columns=["unit"]))


def _obs(value: float, ts: str, vintage: str) -> pd.DataFrame:
    return make_tidy([("cpcb_aqi/aqi/delhi", T(ts), value, "aqi")], "cpcb_aqi", T(vintage))


def test_store_as_of_and_first_release(tmp_path):
    store = VintageStore(tmp_path)
    store.save_observations(_obs(100.0, "2026-10-01", "2026-10-01"))
    store.save_observations(_obs(120.0, "2026-10-01", "2026-10-05"))  # a later revision
    store.save_observations(_obs(90.0, "2026-10-02", "2026-10-02"))

    on_3rd = store.as_of(T("2026-10-03"))
    assert on_3rd.set_index("timestamp").loc[T("2026-10-01"), "value"] == 100.0
    assert store.as_of(T("2026-10-06")).set_index("timestamp").loc[T("2026-10-01"), "value"] == 120.0
    # Nothing published after the as-of date may leak in.
    assert store.as_of(T("2026-10-01"))["timestamp"].max() == T("2026-10-01")
    first = store.first_release().set_index("timestamp")
    assert first.loc[T("2026-10-01"), "value"] == 100.0


def test_store_save_is_idempotent(tmp_path):
    store = VintageStore(tmp_path)
    store.save_observations(_obs(100.0, "2026-10-01", "2026-10-01"))
    store.save_observations(_obs(100.0, "2026-10-01", "2026-10-01"))
    assert len(store.observations()) == 1


class _FakeResponse:
    def __init__(self, status: int, content: bytes = b"") -> None:
        self.status_code, self.content = status, content

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _FakeClient:
    """Serves fixture bytes by URL; anything else is a 404."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def get(self, url: str, **_: object) -> _FakeResponse:
        return _FakeResponse(200, self.files[url]) if url in self.files else _FakeResponse(404)


class _ListedCpcb(Source):
    """CPCB parser with a fixed file list, so the test controls which days exist."""

    def __init__(self, refs: list[FileRef]) -> None:
        self._real = get_source("cpcb_aqi")
        self.info, self.contract, self._refs = self._real.info, self._real.contract, refs

    def list_files(self, client, start, end):
        return self._refs

    def parse(self, content, ref, vintage_date):
        return self._real.parse(content, ref, vintage_date)


def test_fetch_records_missing_bad_and_good_files(tmp_path, fixtures):
    good = FileRef("good", "good.pdf", obs_date=T("2026-10-26"), published=T("2026-10-26"))
    gone = FileRef("gone", "gone.pdf", obs_date=T("2026-10-25"), published=T("2026-10-25"))
    bad = FileRef("bad", "bad.pdf", obs_date=T("2026-10-24"), published=T("2026-10-24"))
    client = _FakeClient({"good": (fixtures / "cpcb_aqi_2026-10-26.pdf").read_bytes(), "bad": b"%PDF-broken"})
    store = VintageStore(tmp_path)
    src = _ListedCpcb([good, gone, bad])

    res = fetch_source(src, T("2026-10-24"), T("2026-10-26"), client=client, store=store, backfill=True)

    assert res.ok_files == 1
    assert res.missing_files == ["gone.pdf"]
    assert len(res.contract_errors) == 1 and "bad.pdf" in res.contract_errors[0]
    assert not res.healthy
    index = store.raw_index()
    assert set(index["status"]) == {"ok", "rejected"}
    # Backfilled rows carry the source's publication date as vintage.
    assert set(store.observations()["vintage_date"]) == {T("2026-10-26")}

    # Fetching the same bytes again adds nothing.
    again = fetch_source(src, T("2026-10-24"), T("2026-10-26"), client=client, store=store, backfill=True)
    assert again.ok_files == 0


def test_fetch_listing_failure_is_reported_not_raised(tmp_path):
    class Broken(_ListedCpcb):
        def list_files(self, client, start, end):
            raise ConnectionError("down")

    res = fetch_source(
        Broken([]), T("2026-10-01"), T("2026-10-02"), client=_FakeClient({}), store=VintageStore(tmp_path)
    )
    assert res.errors and "listing failed" in res.errors[0]
