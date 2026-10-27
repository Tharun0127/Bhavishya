"""Small inline SVG charts. No JavaScript chart library: pages stay fast and work offline."""

from __future__ import annotations

import html

import numpy as np
import pandas as pd

W, H, PAD_L, PAD_R, PAD_T, PAD_B = 640, 260, 52, 12, 12, 28


def _scale(values: np.ndarray, lo: float, hi: float, out_lo: float, out_hi: float) -> np.ndarray:
    span = hi - lo if hi > lo else 1.0
    return out_lo + (values - lo) / span * (out_hi - out_lo)


def _fmt(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}"


def fan_chart(
    history: pd.DataFrame,
    forecast: pd.DataFrame | None,
    actual_after: pd.DataFrame | None,
    title: str,
    unit: str,
) -> str:
    """History line, 80% and 40% forecast bands, median, and later actuals as dots.

    ``history``/``actual_after``: ``timestamp, value``. ``forecast``: ``target_date, q0.1 ... q0.9``.
    """
    xs = list(history["timestamp"])
    ys = list(history["value"])
    if forecast is not None and len(forecast):
        xs += list(forecast["target_date"])
        ys += list(forecast["q0.1"]) + list(forecast["q0.9"])
    if actual_after is not None and len(actual_after):
        xs += list(actual_after["timestamp"])
        ys += list(actual_after["value"])
    t0, t1 = min(xs), max(xs)
    y0, y1 = float(np.nanmin(ys)), float(np.nanmax(ys))
    pad = (y1 - y0) * 0.08 or 1.0
    y0, y1 = y0 - pad, y1 + pad

    def px(ts: pd.Series) -> np.ndarray:
        days = (pd.to_datetime(ts) - t0).dt.days.to_numpy(dtype=float)
        return _scale(days, 0, max((t1 - t0).days, 1), PAD_L, W - PAD_R)

    def py(v: pd.Series) -> np.ndarray:
        return _scale(np.asarray(v, dtype=float), y0, y1, H - PAD_B, PAD_T)

    def path(x: np.ndarray, y: np.ndarray) -> str:
        return " ".join(
            f"{'M' if i == 0 else 'L'}{a:.1f},{b:.1f}" for i, (a, b) in enumerate(zip(x, y, strict=True))
        )

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}" class="chart">']
    for frac in (0.0, 0.5, 1.0):  # three light gridlines with labels
        v = y0 + frac * (y1 - y0)
        yy = py(pd.Series([v]))[0]
        parts.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{yy:.1f}" y2="{yy:.1f}" class="grid"/>')
        parts.append(
            f'<text x="{PAD_L - 6}" y="{yy + 4:.1f}" class="axis" text-anchor="end">{_fmt(v)}</text>'
        )
    parts.append(f'<text x="{PAD_L}" y="{H - 8}" class="axis">{t0:%d %b %Y}</text>')
    parts.append(f'<text x="{W - PAD_R}" y="{H - 8}" class="axis" text-anchor="end">{t1:%d %b %Y}</text>')
    parts.append(f'<text x="4" y="{PAD_T + 10}" class="axis">{html.escape(unit)}</text>')
    if forecast is not None and len(forecast):
        fx = px(forecast["target_date"])
        for lo, hi, cls in (("q0.1", "q0.9", "band80"), ("q0.3", "q0.7", "band40")):
            top, bot = py(forecast[hi]), py(forecast[lo])
            pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(fx, top, strict=True))
            pts += " " + " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(fx[::-1], bot[::-1], strict=True))
            parts.append(f'<polygon points="{pts}" class="{cls}"/>')
        parts.append(f'<path d="{path(fx, py(forecast["q0.5"]))}" class="median"/>')
    parts.append(f'<path d="{path(px(history["timestamp"]), py(history["value"]))}" class="hist"/>')
    if actual_after is not None and len(actual_after):
        for a, b in zip(px(actual_after["timestamp"]), py(actual_after["value"]), strict=True):
            parts.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="2.6" class="actual"/>')
    parts.append("</svg>")
    return "".join(parts)


def interval_chart(rows: pd.DataFrame, title: str) -> str:
    """Horizontal point-and-interval chart of relative skill (1 = seasonal naive)."""
    rows = rows.dropna(subset=["crps_skill"])
    if rows.empty:
        return ""
    h = 28 * len(rows) + 40
    vals = np.concatenate(
        [
            rows["crps_skill"],
            rows["crps_lo"].fillna(rows["crps_skill"]),
            rows["crps_hi"].fillna(rows["crps_skill"]),
            [1.0],
        ]
    )
    lo, hi = float(np.nanmin(vals)) * 0.95, float(np.nanmax(vals)) * 1.05
    left = 130

    def px(v: float) -> float:
        return float(_scale(np.asarray([v]), lo, hi, left, W - 20)[0])

    parts = [
        f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{html.escape(title)}" class="chart">',
        f'<line x1="{px(1.0):.1f}" x2="{px(1.0):.1f}" y1="10" y2="{h - 24}" class="ref"/>',
        f'<text x="{px(1.0):.1f}" y="{h - 8}" class="axis" text-anchor="middle">1.0 = seasonal naive</text>',
    ]
    for i, r in enumerate(rows.to_dict("records")):
        y = 24 + 28 * i
        skill, ci_lo, ci_hi = float(r["crps_skill"]), float(r["crps_lo"]), float(r["crps_hi"])
        parts.append(
            f'<text x="{left - 8}" y="{y + 4}" class="axis" text-anchor="end">{html.escape(str(r["model"]))}</text>'
        )
        if np.isfinite(ci_lo) and np.isfinite(ci_hi):
            parts.append(f'<line x1="{px(ci_lo):.1f}" x2="{px(ci_hi):.1f}" y1="{y}" y2="{y}" class="ci"/>')
        parts.append(f'<circle cx="{px(skill):.1f}" cy="{y}" r="4" class="pt"/>')
        parts.append(f'<text x="{px(skill) + 8:.1f}" y="{y - 6}" class="axis">{skill:.2f}</text>')
    parts.append("</svg>")
    return "".join(parts)
