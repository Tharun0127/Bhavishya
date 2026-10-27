"""Static site generator: leaderboard, per-series pages, methodology, data and status pages.

Every chart title states its takeaway, computed from the data, so a reader gets the point
without decoding the chart. No external scripts, fonts or trackers.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd
from jinja2 import Environment, select_autoescape

from bhavishya.arena import leaderboard as lb
from bhavishya.arena.charts import fan_chart, interval_chart
from bhavishya.arena.hashing import read_manifest
from bhavishya.arena.health import build_status
from bhavishya.arena.panel import Panel
from bhavishya.models.registry import REFERENCE_MODEL
from bhavishya.sources import SOURCES
from bhavishya.store import VintageStore

REPO = "https://github.com/Tharun0127/Bhavishya"
DATA_BRANCH = f"{REPO}/tree/data"

CSS = """
:root{--bg:#fff;--fg:#1d1f23;--muted:#5d6470;--line:#e3e6ea;--accent:#1f5fbf;--band:#1f5fbf;--warn:#9a5b00}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--fg:#e8eaed;--muted:#a0a7b1;--line:#2c3036;--accent:#7fb0ff;--band:#7fb0ff;--warn:#e0a84a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:980px;margin:0 auto;padding:16px}header{border-bottom:1px solid var(--line)}
nav{max-width:980px;margin:0 auto;padding:12px 16px;display:flex;flex-wrap:wrap;gap:14px;align-items:baseline}
nav a{color:var(--fg);text-decoration:none}nav .brand{font-weight:700;margin-right:auto}a{color:var(--accent)}
h1{font-size:1.6rem;margin:.6rem 0}h2{font-size:1.2rem;margin-top:2rem}.muted{color:var(--muted)}
.note{border-left:3px solid var(--warn);padding:.4rem .8rem;margin:1rem 0;color:var(--fg)}
.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}
.chart{width:100%;height:auto}.chart .grid{stroke:var(--line)}.chart .axis{fill:var(--muted);font-size:11px}
.chart .hist{fill:none;stroke:var(--fg);stroke-width:1.4}.chart .median{fill:none;stroke:var(--band);stroke-width:2}
.chart .band80{fill:var(--band);opacity:.15}.chart .band40{fill:var(--band);opacity:.25}.chart .actual{fill:#d0453a}
.chart .ref{stroke:var(--muted);stroke-dasharray:4 3}.chart .ci{stroke:var(--band);stroke-width:2}.chart .pt{fill:var(--band)}
select{font:inherit;padding:4px}figure{margin:1rem 0}figcaption{font-weight:600;margin-bottom:.3rem}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}code{font-size:.9em;word-break:break-all}
"""

BASE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }} | Bhavishya</title>
<meta name="description" content="Bhavishya: the live forecasting arena for India.">
<style>{{ css }}</style></head><body><header><nav><a class="brand" href="{{ root }}index.html">Bhavishya</a>
<a href="{{ root }}index.html">Leaderboard</a><a href="{{ root }}series.html">Series</a>
<a href="{{ root }}methodology.html">Methodology</a><a href="{{ root }}data.html">Data</a>
<a href="{{ root }}status.html">Status</a><a href="{{ repo }}">Code</a></nav></header>
<main>{{ body | safe }}<p class="muted" style="margin-top:3rem">Data: Grid-India daily PSP reports; CPCB daily AQI
bulletins. Values are republished as derived daily figures with attribution. Built {{ built }}.</p></main></body></html>"""


def _env() -> Environment:
    return Environment(autoescape=select_autoescape(default=True))


def _page(out: Path, name: str, title: str, body: str, depth: int = 0) -> None:
    root = "../" * depth
    page = (
        _env()
        .from_string(BASE)
        .render(
            title=title,
            css=CSS,
            body=body,
            root=root,
            repo=REPO,
            built=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M UTC"),
        )
    )
    path = out / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


def slug(series_id: str) -> str:
    return series_id.replace("/", "__")


def _table(df: pd.DataFrame, formats: dict[str, str]) -> str:
    head = "".join(f"<th>{html.escape(c)}</th>" for c in df.columns)
    body = []
    for row in df.itertuples(index=False):
        cells = []
        for col, v in zip(df.columns, row, strict=True):
            fmt = formats.get(col)
            text = "" if (isinstance(v, float) and pd.isna(v)) else (fmt.format(v) if fmt else str(v))
            cells.append(f"<td>{html.escape(text)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def leaderboard_takeaway(board: pd.DataFrame) -> str:
    if board.empty:
        return "No forecasts have been scored yet"
    ranked = board[board["eligible"]]
    if ranked.empty:
        return (
            f"No model is ranked yet: ranking needs {lb.MIN_DAYS_LIVE} days live and "
            f"{lb.MIN_SCORED:,} scored forecasts"
        )
    top = ranked.iloc[0]
    pct = (1 - top["crps_skill"]) * 100
    word = "better" if pct > 0 else "worse"
    return (
        f"{top['model']} leads, {abs(pct):.0f}% {word} than seasonal naive on scaled CRPS "
        f"(95% interval {top['crps_lo']:.2f} to {top['crps_hi']:.2f})"
    )


def fan_takeaway(model: str, last_value: float, fc: pd.DataFrame, unit: str) -> str:
    end = fc.iloc[-1]
    change = (end["q0.5"] - last_value) / last_value * 100 if last_value else 0.0
    direction = "about flat" if abs(change) < 3 else ("up" if change > 0 else "down")
    return (
        f"{model}: median {direction} ({change:+.0f}%) by {end['target_date']:%d %b}, "
        f"80% band {end['q0.1']:,.0f} to {end['q0.9']:,.0f} {unit}"
    )


def build_site(store: VintageStore, panel: Panel, docs: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(store.root)
    forecasts = (
        pd.concat([pd.read_parquet(store.root / p) for p in manifest["path"]], ignore_index=True)
        if len(manifest)
        else pd.DataFrame()
    )
    scores_path = store.root / "scores" / "scores.parquet"
    scores = pd.read_parquet(scores_path) if scores_path.exists() else pd.DataFrame()
    obs = store.as_of(pd.Timestamp.max.normalize(), panel.sources)
    obs = obs[obs["series_id"].isin(panel.series)]

    _build_index(out, forecasts, scores)
    _build_series(out, panel, obs, forecasts, scores)
    _build_methodology(out, docs)
    _build_data(out, panel, manifest)
    _build_status(out, store)


def _build_index(out: Path, forecasts: pd.DataFrame, scores: pd.DataFrame) -> None:
    days_live = (
        {str(k): int(v) for k, v in forecasts.groupby("model")["run_date"].nunique().items()}
        if len(forecasts)
        else {}
    )
    first_run = f"{forecasts['run_date'].min():%d %b %Y}" if len(forecasts) else "not started"
    parts = [
        "<h1>Bhavishya leaderboard</h1>",
        "<p>Models forecast Indian power demand and city air quality before the numbers exist. Every forecast "
        "file is hashed and committed to git first, then scored against the first published value.</p>",
        '<p class="note">Limitations: young benchmark, few series, two sources. Rankings are provisional until '
        f"each model has {lb.MIN_DAYS_LIVE} days live and {lb.MIN_SCORED:,} scored forecasts. "
        "See the methodology page.</p>",
        f'<p class="muted">First forecast run: {first_run}. Models: {len(days_live)}. '
        f"Scored forecasts: {len(scores):,}.</p>",
    ]
    if scores.empty:
        parts.append(
            "<h2>No forecasts have been scored yet</h2><p>Scores appear the day after the first "
            "outcomes are published.</p>"
        )
        rows = [{"model": m, "days_live": d} for m, d in sorted(days_live.items())]
        if rows:
            parts.append(_table(pd.DataFrame(rows), {}))
    else:
        board = lb.leaderboard(scores, days_live)
        title = leaderboard_takeaway(board)
        parts.append(
            f"<figure><figcaption>{html.escape(title)}</figcaption>{interval_chart(board, title)}</figure>"
        )
        parts.append(_filters_block(scores, board))
    _page(out, "index.html", "Leaderboard", "".join(parts))


def _filters_block(scores: pd.DataFrame, board: pd.DataFrame) -> str:
    """Overall table plus one table per source and horizon bucket; a select shows one at a time."""
    cols = [
        "rank",
        "model",
        "days_live",
        "n_scored",
        "crps_skill",
        "crps_lo",
        "crps_hi",
        "mase_skill",
        "coverage_80",
    ]
    fmts = {
        "rank": "{:.0f}",
        "crps_skill": "{:.3f}",
        "crps_lo": "{:.3f}",
        "crps_hi": "{:.3f}",
        "mase_skill": "{:.3f}",
        "coverage_80": "{:.0%}",
        "n_scored": "{:,}",
    }
    blocks = {"all": _table(board[cols], fmts)}
    options = ['<option value="all">All series, all horizons</option>']
    for by in ("source", "horizon_bucket"):
        part = lb.breakdown(scores, by)
        for value, sub in part.groupby(by):
            key = f"{by}-{value}"
            label = f"Source: {value}" if by == "source" else f"Horizon {value} days"
            options.append(f'<option value="{html.escape(key)}">{html.escape(label)}</option>')
            sub = sub.sort_values("crps_skill")[
                ["model", "n_scored", "crps_skill", "crps_lo", "crps_hi", "coverage_80"]
            ]
            blocks[key] = _table(sub, fmts)
    divs = "".join(
        f'<div class="lbview" data-view="{html.escape(k)}"{"" if k == "all" else " hidden"}>{v}</div>'
        for k, v in blocks.items()
    )
    script = (
        "<script>document.getElementById('lbfilter').addEventListener('change',function(e){"
        "document.querySelectorAll('.lbview').forEach(function(d){d.hidden=d.dataset.view!==e.target.value})})"
        "</script>"
    )
    return (
        f"<h2>Skill relative to {REFERENCE_MODEL} (lower is better)</h2>"
        f'<label>View <select id="lbfilter">{"".join(options)}</select></label>{divs}{script}'
        '<p class="muted">crps_skill: geometric mean over series of the ratio of scaled CRPS to seasonal naive. '
        "Brackets are 95% block-bootstrap intervals over run dates. coverage_80 should be near 80%.</p>"
    )


def _build_series(
    out: Path, panel: Panel, obs: pd.DataFrame, forecasts: pd.DataFrame, scores: pd.DataFrame
) -> None:
    items = []
    latest_run = forecasts["run_date"].max() if len(forecasts) else None
    per_series = lb.per_series(scores) if len(scores) else pd.DataFrame()
    for sid in panel.series:
        hist_all = obs[obs["series_id"] == sid].sort_values("timestamp")
        if hist_all.empty:
            continue
        unit = str(hist_all["unit"].iloc[-1])
        items.append(f'<li><a href="series/{slug(sid)}.html">{html.escape(sid)}</a></li>')
        figs = []
        if latest_run is not None:
            fc_all = forecasts[(forecasts["series_id"] == sid) & (forecasts["run_date"] == latest_run)]
            for model, fc in fc_all.groupby("model"):
                cutoff = fc["cutoff"].iloc[0]
                hist = hist_all[
                    (hist_all["timestamp"] <= cutoff)
                    & (hist_all["timestamp"] > cutoff - pd.Timedelta(days=90))
                ]
                after = hist_all[hist_all["timestamp"] > cutoff]
                title = fan_takeaway(
                    str(model), float(hist["value"].iloc[-1]), fc.sort_values("horizon"), unit
                )
                figs.append(
                    f"<figure><figcaption>{html.escape(title)}</figcaption>"
                    f"{fan_chart(hist, fc, after, title, unit)}</figure>"
                )
        body = [
            f"<h1>{html.escape(sid)}</h1>",
            f'<p class="muted">Unit: {html.escape(unit)}. Latest value {hist_all["value"].iloc[-1]:,.1f} on '
            f"{hist_all['timestamp'].iloc[-1]:%d %b %Y}. Bands: 80% (light) and 40% (dark); red dots are "
            "actuals published after the forecast.</p>",
        ]
        if figs:
            body.append(
                f'<h2>Latest forecasts (run {latest_run:%d %b %Y})</h2><div class="grid2">{"".join(figs)}</div>'
            )
        else:
            last = hist_all.tail(120)
            title = f"{sid}: no forecasts yet; last 120 days shown"
            body.append(
                f"<figure><figcaption>{html.escape(title)}</figcaption>{fan_chart(last, None, None, title, unit)}"
                "</figure>"
            )
        if len(per_series):
            sub = (
                per_series[per_series["series_id"] == sid]
                .drop(columns="series_id")
                .sort_values("mean_scaled_crps")
            )
            if len(sub):
                body.append(
                    "<h2>Scores so far</h2>"
                    + _table(
                        sub, {"mean_scaled_crps": "{:.3f}", "mean_mase": "{:.3f}", "coverage_80": "{:.0%}"}
                    )
                )
        _page(out, f"series/{slug(sid)}.html", sid, "".join(body), depth=1)
    _page(out, "series.html", "Series", "<h1>Series in the launch panel</h1><ul>" + "".join(items) + "</ul>")


def _build_methodology(out: Path, docs: Path) -> None:
    import markdown

    text = (docs / "METHODOLOGY.md").read_text(encoding="utf-8") if (docs / "METHODOLOGY.md").exists() else ""
    _page(out, "methodology.html", "Methodology", markdown.markdown(text, extensions=["tables", "toc"]))


def _build_data(out: Path, panel: Panel, manifest: pd.DataFrame) -> None:
    rows = pd.DataFrame(
        [
            {
                "source": s.name,
                "publisher": s.publisher,
                "release": s.release_lag,
                "attribution": s.attribution,
            }
            for s in (SOURCES[n].info for n in SOURCES)
        ]
    )
    body = [
        "<h1>Data</h1>",
        "<p>Install the loaders with <code>pip install bhavishya</code> (after the first release) or from GitHub. "
        f'Licences and caveats: <a href="{REPO}/blob/main/DATA_SOURCES.md">DATA_SOURCES.md</a>.</p>',
        _table(rows, {}),
        f"<h2>Launch panel ({len(panel.series)} series, frozen {panel.frozen_on:%d %b %Y})</h2>",
        f'<p><a href="{REPO}/blob/main/config/panel.yaml">config/panel.yaml</a> lists the series and the rules '
        "that chose them.</p>",
        "<h2>Forecast manifest</h2>",
        f'<p>All forecasts, inputs, scores and the hash manifest live on the <a href="{DATA_BRANCH}">data branch</a>. '
        "To verify a file: download it, compute its SHA-256, and compare with the line below and with the git "
        "commit time. <code>bhavishya arena verify</code> does this for every file.</p>",
    ]
    if len(manifest):
        body.append(_table(manifest[["run_date", "sha256", "n_rows", "models"]].tail(60).iloc[::-1], {}))
    _page(out, "data.html", "Data", "".join(body))


def _build_status(out: Path, store: VintageStore) -> None:
    status = build_status(store.root)
    src = pd.DataFrame([{"source": k, **v} for k, v in status["sources"].items()])
    mod = pd.DataFrame([{"model": k, **v} for k, v in status["models"].items()])
    failing = [] if src.empty else list(src.loc[src["last_state"] != "ok", "source"])
    title = (
        "All sources healthy on the last run"
        if not failing
        else f"Skipped on the last run: {', '.join(failing)}"
    )
    body = [
        f"<h1>Status</h1><h2>{html.escape(title)}</h2>",
        _table(src, {}) if len(src) else "<p>No live fetch has run yet.</p>",
        "<h2>Models: last successful run</h2>",
        _table(mod, {}) if len(mod) else "<p>No runs yet.</p>",
        f'<p class="muted">Generated {status["generated_at_utc"]}.</p>',
    ]
    _page(out, "status.html", "Status", "".join(body))
    (out / "status.json").write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")
