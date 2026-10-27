"""Source health decisions, the gap log, issue bodies and the status summary."""

from __future__ import annotations

import json

import pandas as pd

from bhavishya.arena import health
from bhavishya.contracts import empty_tidy, make_tidy
from bhavishya.fetch import FetchResult
from bhavishya.sources import get_source

T = pd.Timestamp
SRC = get_source("cpcb_aqi")


def _asof(newest: str) -> pd.DataFrame:
    return make_tidy([("cpcb_aqi/aqi/delhi", T(newest), 100.0, "aqi")], "cpcb_aqi", T(newest))


def test_judge_states():
    run = T("2026-10-27")
    ok = FetchResult("cpcb_aqi", empty_tidy(), ok_files=1)
    assert health.judge(ok, _asof("2026-10-26"), SRC, run).state == "ok"
    assert health.judge(ok, _asof("2026-10-20"), SRC, run).state == "stale"
    assert health.judge(ok, empty_tidy(), SRC, run).state == "stale"
    failed = FetchResult("cpcb_aqi", empty_tidy(), errors=["listing failed"])
    assert health.judge(failed, _asof("2026-10-26"), SRC, run).state == "failed"
    broken = FetchResult("cpcb_aqi", empty_tidy(), contract_errors=["x.pdf: bad"])
    assert health.judge(broken, _asof("2026-10-26"), SRC, run).state == "contract"


def test_record_writes_gap_log_and_issue_bodies(tmp_path):
    report = {
        "cpcb_aqi": health.SourceHealth("cpcb_aqi", "stale", "old", "2026-10-20"),
        "grid_india": health.SourceHealth("grid_india", "ok", "1 new file", "2026-10-26"),
    }
    health.record(tmp_path, T("2026-10-27"), report)
    log = pd.read_csv(tmp_path / "health" / "source_health.csv")
    assert list(log["state"]) == ["stale", "ok"]
    issues = list((tmp_path / "health" / "open_issues").glob("*.md"))
    assert [p.stem for p in issues] == ["cpcb_aqi"]
    assert "skipped `cpcb_aqi`" in issues[0].read_text()

    # Next day both healthy: the open issue body is removed, the log keeps the gap.
    health.record(tmp_path, T("2026-10-28"), {k: health.SourceHealth(k, "ok") for k in report})
    assert not list((tmp_path / "health" / "open_issues").glob("*.md"))
    status = health.build_status(tmp_path)
    assert status["sources"]["cpcb_aqi"]["last_success"] == "2026-10-28"
    assert status["sources"]["cpcb_aqi"]["gaps_last_30_runs"] == 1
    json.dumps(status)  # must be serialisable for status.json
