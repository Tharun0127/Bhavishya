# Evaluation methodology

This document describes the evaluation protocol in enough detail to critique it. The code is the reference: file paths are given for each rule. When this text and the code disagree, the code is what ran, and the disagreement is a bug to report.

## 1. What is being evaluated

Probabilistic forecasts of daily Indian public time series, made before the outcomes exist. Each model gives 9 quantiles (0.1, 0.2, ..., 0.9) for each of the next 28 days.

The arena does not evaluate backtests. Every scored forecast was committed to git before its outcome was published.

## 2. Data and vintages

- Sources: Grid-India daily Power Supply Position reports and the CPCB daily AQI bulletin (`DATA_SOURCES.md`).
- Every row in the store has a `vintage_date`: the date the value became public, as far as we know.
  - Live fetches: the IST date of the fetch.
  - History loaded before launch (backfill): the source's own publication date. For Grid-India this is the upload date in the file listing. For CPCB it is the bulletin date, because the bulletin is published that evening.
- `store.as_of(D)` returns, for each observation, the latest value with vintage on or before D. Model inputs for run date D come only from `as_of(D)` (`src/bhavishya/store.py`, `src/bhavishya/arena/daily.py`).
- Raw files are hashed (SHA-256) and the hash is logged in `raw_index.csv`. The raw Grid-India and CPCB files are not republished (see `docs/DECISIONS.md` D5). Anyone can download a file from the source and compare the hash.

## 3. The panel

- Fixed before any forecast, by written rules (`config/panel_rules.yaml`, committed before the first forecast run).
- Rules use only data with vintage on or before the freeze date (2026-10-27): coverage of at least 85% over the prior 365 days; for Grid-India, the all-India totals plus the 15 states with the highest mean energy met; for CPCB, the first 20 cities with enough coverage in the 2011 Census ranking of urban agglomerations.
- No rule looks at volatility, past forecast errors or later values.
- The panel is versioned. A new panel gets a new version and a new start date. Scores from different panel versions are not pooled.

## 4. The daily cycle

All dates are IST calendar dates. The scheduled run is at 11:15 IST.

1. **Fetch.** Download files published in the last 10 days that are not already stored (same SHA-256 means not new). Check each file against the source's data contract (schema, units, ranges, minimum row count).
2. **Health.** A source is skipped for the day if its listing or download failed, a file broke its contract, or its newest value is older than its staleness limit (3 days for both sources). The skip is logged in `health/source_health.csv` and a GitHub issue is opened. Other sources and models continue.
3. **Prepare.** For each healthy source, take `as_of(run_date)`, restricted to panel series.
   - The source cutoff is the newest timestamp among its panel series.
   - A series whose newest value is more than 2 days before the cutoff is skipped for the day.
   - A series with fewer than 90 days of history is skipped.
   - Each remaining series is put on a daily grid up to the cutoff. Missing days are filled with the previous value (forward fill). The number of filled values is recorded in `prepared.json`.
   - The MASE scale for each series is computed from this same history (section 6) and saved with the inputs.
4. **Run models.** Each model runs in its own process (and in CI its own job) on the prepared file. The process receives only that file. `Forecaster.forecast` refuses history that extends past the cutoff (`LeakageError`). Output is checked: one row per series and horizon, finite values. Crossing quantiles are sorted.
5. **Commit.** Outputs from all successful models are merged into `forecasts/<run_date>/forecasts.parquet`. Its SHA-256 is appended to `manifest.csv`, which is append-only. An OpenTimestamps proof is requested. The data branch is pushed.

Typical timing at the 11:15 IST run on day R:

- Grid-India: the report for R-1 appeared around 09:40 IST on R. The cutoff is R-1. Horizon 1 is day R, which cannot exist before midnight at the end of R.
- CPCB: the bulletin for R-1 appeared on the evening of R-1. The bulletin for R does not exist yet, because its 24-hour average ends at 16:00 IST on R. The cutoff is R-1 and horizon 1 is R.

So every target is still in the future at commit time, by at least 4 hours 45 minutes (CPCB horizon 1).

## 5. Which actual value is used

Forecasts are scored against the **first-released** value of each target: the earliest vintage in the store for that series and date (`store.first_release`).

Reasons:

- It is the value that existed when the outcome first became public. Scoring is then fixed once and does not drift when a source revises history.
- Later revisions mix forecast error with revision noise.

The scoring job also checks, row by row, that each forecast was prospective (`is_prospective` in `src/bhavishya/arena/scoring.py`):

- **Time check.** The commit time (from the manifest) must be before the earliest instant the target value could exist: 16:00 IST on the target date for CPCB (the end of its 24-hour averaging window), and midnight after the target date for Grid-India. Comparing dates alone is not enough, because CPCB publishes day D's value on day D. A delayed run that commits after 16:00 IST therefore loses its CPCB horizon-1 rows automatically.
- **Vintage check.** The stored actual must not have a vintage before the run date.

Rows failing either check are dropped and counted.

Replays (pipeline tests) record a simulated commit time of 11:15 IST on the replayed date and are flagged `replay: true` in `run.json`. They never enter the live record. A replay on date D can see CPCB's bulletin for D, which a real 11:15 run could not, so replays are slightly optimistic for CPCB. This affects pipeline tests only.

Limitation: for backfilled history we infer vintages from publication metadata. Values revised before our first fetch are not visible to us.

## 6. Metrics

For one forecast (series s, run date r, horizon h) with actual y, median m and quantiles q_k at levels tau_k:

- **Absolute error:** |y - m|.
- **MASE:** |y - m| / scale_s,r, where scale_s,r is the mean absolute 7-day seasonal difference of the series' history up to the cutoff. The scale is computed at prepare time and committed with the inputs, so it cannot be tuned later.
- **CRPS (quantile approximation):** (1/9) * sum_k 2 * pinball(y, q_k, tau_k), where pinball(y, q, tau) = max(tau (y - q), (tau - 1)(y - q)). For a point forecast this equals the absolute error.
- **Scaled CRPS:** CRPS / scale_s,r. This is the primary metric.
- **80% coverage:** 1 if q_0.1 <= y <= q_0.9, else 0. A calibrated model should cover about 80%.

Series with a zero scale (flat history) get no scaled metrics.

Code: `src/bhavishya/arena/scoring.py`. Known-answer tests: `tests/test_scoring.py`.

## 7. Aggregation and ranking

- **Pairing.** A model is compared with seasonal naive only on forecasts both made: same series, run date and horizon. A model that skips hard days cannot gain from it.
- **Relative score.** For each series: the model's mean scaled CRPS divided by seasonal naive's mean scaled CRPS on the paired forecasts. The model's skill is the geometric mean of these ratios across series. Below 1 is better than seasonal naive. The same is computed for MASE.
- **Why the geometric mean:** a ratio of 0.5 on one series and 2.0 on another averages to 1.0, as it should. One large series cannot dominate.
- **Uncertainty.** 95% intervals from a block bootstrap: resample whole run dates with replacement (1,000 draws), recompute the skill. Days are the blocks because errors on the same day are correlated across series and horizons. Overlapping horizons across consecutive days induce further correlation that daily blocks do not fully capture, so the intervals are somewhat too narrow.
- **Breakdowns.** By source, by horizon bucket (1-7, 8-14, 15-28 days), and per series (means only).
- **Ranking rule.** A model is ranked only after both 28 days live (distinct run dates with a committed forecast) and 10,000 scored forecasts. Before that it is listed as provisional, without a rank. The leaderboard shows days live and scored count for every model.
- **Late entrants.** A model entering later is compared on its own paired days only. Its days live count from its first committed forecast. Past days are never backfilled.

Code: `src/bhavishya/arena/leaderboard.py`.

## 8. Models

| Model | Type | Notes |
|---|---|---|
| seasonal_naive | reference | repeats the last 7 days; intervals from statsforecast |
| auto_ets, auto_arima | local statistical | statsforecast, season 7, last 730 days |
| lightgbm | global ML | one model per source, lags 1-28, per-series scaling, conformal intervals from 3 windows |
| chronos2 | foundation, zero-shot | `amazon/chronos-2` at a pinned revision |
| timesfm2_5 | foundation, zero-shot | `google/timesfm-2.5-200m-pytorch` at a pinned revision |
| moirai2 | foundation, zero-shot | `Salesforce/moirai-2.0-R-small` at a pinned revision, own environment |

Statistical models turn central prediction intervals (20, 40, 60, 80%) into the 9 quantiles. Foundation models get up to 1,024 days of context. Weight file hashes are recorded with every run. No covariates are used at launch.

## 9. Tamper evidence

- The forecast file for run date r is pushed before any of its targets is published (section 4).
- The manifest line with its SHA-256 is in the same push.
- An OpenTimestamps proof anchors the hash in Bitcoin within hours.
- `bhavishya verify` recomputes every hash. Scoring refuses to run if any hash fails.

What this does not prove: that the model really ran as described. It proves only that the forecasts existed at that time and were not changed later. The inputs and their hashes are committed too, so anyone can re-run the open models and compare.

## 10. Known weaknesses

- Short history at launch. Rankings will be noisy for months.
- Two sources, about 37 series, one country. Results do not generalise to other domains.
- Seasonal naive is a weak reference for some series (for example AQI in winter onset). Relative skill can look large for that reason.
- Forward-filling gaps creates flat stretches that can help naive models slightly.
- Foundation models may have seen older parts of these series in pretraining. The prospective design removes contamination of the targets, not of the history.
- Quantile CRPS with 9 levels is an approximation and ignores the tails beyond 10% and 90%.
- Vintages for backfilled history are inferred from metadata, not observed.
- Bootstrap intervals assume run dates are exchangeable blocks. Seasonality across the year breaks that assumption.
