# Paper outline (to write after 90 days live)

Status: **No results yet.** The arena launched on 2026-10-27. This file plans the paper. Every analysis below runs on data that does not exist yet. Nothing here is a finding.

Planned analysis date: after the 90th run date (on or after 2027-01-25), once the last 28-day horizon from the analysis window has also been scored. Target writing date: late February 2027.

Working title: *Bhavishya: a prospective, hash-committed benchmark of time series foundation models on Indian public data*

Author: Tharun0127 (and any contributors who submit models or analyses and want to be listed).

---

## 0. Ground rules for the paper

1. **Freeze the analysis before looking.** Commit this outline and the analysis scripts to `main` before running them on the full 90 days. Any analysis added later is labelled "exploratory" in the paper.
2. **One panel version.** Use panel `v1` only (config/panel_rules.yaml). Never mix scores across panel versions.
3. **One scoring rule.** Primary results use first-release actuals, as the arena does. Latest-vintage scoring is a secondary analysis (section 6.5).
4. **Report everything that ran.** Every model in the registry is in every table, including the ones that look bad. Failed runs are counted, not hidden.
5. **Cite prior art first.** The introduction states what is not new before stating what is (docs/PRIOR_ART.md section 6).

---

## 1. Abstract (write last)

Four sentences: what the benchmark is, what was run, the headline comparison with uncertainty, and the main limitation. No number goes in the abstract that is not in a table with a confidence interval.

## 2. Introduction

- Problem: static forecasting benchmarks reuse public datasets. Foundation models are trained on large web-scale corpora that may include those datasets or correlated series. A static score can therefore measure memory as well as skill (Meyer et al., arXiv 2510.13654).
- Prospective evaluation removes this risk for the evaluation window: the target value did not exist when the forecast was made.
- Indian public series are under-represented in live benchmarks. TS-Arena, Impermanent and LiveHouse-TS use German, US, Finnish, GitHub and mostly global sources.
- Contributions (stated narrowly):
  1. A 90-day prospective evaluation of seven models (four statistical or machine learning baselines, three foundation models) on Grid-India daily state energy met and CPCB daily city AQI.
  2. Forecast files hashed (SHA-256), committed to a public git branch and timestamped with OpenTimestamps before outcomes exist. Anyone can verify timing without trusting the maintainer.
  3. Scoring against first-released values, with a vintage store that keeps every revision, so the effect of revisions can be measured.
  4. Open, pip-installable loaders for both sources with vintage-dated snapshots.
- What is not new: live TSFM benchmarks, live CRPS scoring, hash commit-reveal for forecasts in general, TSFM evaluation on CPCB data (Air Quality Arena, static). Cite each.

## 3. Related work

Copy the structure of docs/PRIOR_ART.md sections 2 to 4, condensed. Recheck every entry before submission, because several close works appeared in 2026. Mark anything still unverified.

## 4. Data

### 4.1 Sources

| Source | Series | Unit | Release | Notes |
|---|---|---|---|---|
| Grid-India daily PSP report | all-India energy met, all-India max demand, energy met for 15 states | MU, MW | day D+1, usually before 10:00 IST | XLS parsed from section A and section C |
| CPCB daily AQI bulletin | National AQI for up to 20 cities | unitless, 0 to 500 | evening of day D, 24-hour average to 16:00 IST | PDF tables |

Open-Meteo is fetched but is not a target (docs/DECISIONS.md D3). Agmarknet is deferred (needs a data.gov.in key).

### 4.2 Panel selection

Describe the written rules (config/panel_rules.yaml): coverage of at least 0.85 over 365 days, largest states by mean energy met, cities in 2011 Census order. State that the rules use only data with vintage on or before the freeze date and look at no forecast error or volatility.

### 4.3 Vintages and first release

Explain `VintageStore.as_of` and `VintageStore.first_release` (src/bhavishya/store.py). Explain how live vintages (fetch date) differ from backfill vintages (source publication date).

### 4.4 Data quality during the window

Table T1 (see section 8): per source, run days, healthy days, skipped days by reason (`failed`, `contract`, `stale`), files rejected by contract, values forward-filled in model inputs.

## 5. Arena design

- Daily cycle (src/bhavishya/arena/daily.py): fetch, health check, prepare inputs truncated at the cutoff, one process per model, merge, hash, manifest, OpenTimestamps, push.
- Leakage controls: truncation before the input file is written; `check_no_leakage` in `Forecaster.forecast`; process isolation; the `prospective` check in scoring.
- Commitment: manifest line and file pushed before any target value exists; `bhavishya verify` recomputes all hashes before scoring.
- Models: seasonal naive (season 7), AutoETS, AutoARIMA (statsforecast), LightGBM global with conformal intervals (mlforecast), Chronos-2, TimesFM 2.5 (200M), Moirai 2.0 small. Pinned versions, Hugging Face revisions and weight hashes from `run.json`.
- Why TimesFM 3.0 is not included: non-commercial licence and code not on PyPI at launch.
- Horizon 1 to 28 days. Nine quantiles 0.1 to 0.9.

## 6. Research questions and analyses

Each research question lists the exact analysis, the script that will produce it, and the output files. Scripts go in `analysis/` (not yet written). All bootstrap intervals use a fixed seed and report the seed.

### RQ1. Do zero-shot foundation models beat simple baselines on these Indian series, prospectively?

**6.1 Skill by source and horizon**

- Metric: scaled CRPS skill and MASE skill relative to seasonal naive, geometric mean over series of per-series mean ratios (as in src/bhavishya/arena/leaderboard.py).
- Splits: overall; by source (`grid_india`, `cpcb_aqi`); by horizon bucket (1-7, 8-14, 15-28); by single horizon 1 to 28 for the figure.
- Uncertainty: 95% block bootstrap over run dates, 2,000 draws (the site uses 1,000). Also report a moving-block bootstrap with block length 7 and 28 run days, because forecasts from nearby run dates share target dates (see 6.2 caveat).
- Output: T2, T3, F1, F2.

**6.2 Pairwise and set comparisons**

- Diebold-Mariano style test on the daily mean of scaled CRPS (per run date, averaged over series and horizons) for each model pair. Use a HAC (Newey-West) variance with lag at least 27, because loss series from run dates up to 27 days apart share target dates. Report the Harvey-Leybourne-Newbold small-sample correction.
- Model confidence set (Hansen, Lunde and Nason) at 90%, using a block bootstrap on the same daily loss series, block length 28.
- **Caveat on dependence.** Losses are correlated across series on the same day (shared weather, holidays, festivals, national grid events) and across run dates (overlapping horizons). The tests above handle serial dependence only approximately. With about 90 run dates, the effective sample size is small. We will state that p-values are indicative, report intervals rather than stars, and never claim a ranking that the interval does not support.
- Output: T4, T5.

### RQ2. Are the probabilistic forecasts calibrated?

**6.3 Calibration**

- 80% interval coverage (q0.1 to q0.9) by model, source and horizon bucket. Nominal is 0.80.
- Coverage of every central interval the nine quantiles define (20%, 40%, 60%, 80%), as a reliability diagram.
- PIT histogram from quantiles: for each forecast, find which of the 10 bins between and beyond the nine quantiles the actual falls into. Under calibration each bin has probability 0.1. Plot per model and source. Test uniformity with a chi-square test, with the same dependence caveat as 6.2.
- Coverage by single horizon (1 to 28), to see whether intervals widen fast enough.
- Output: T6, F3, F4, F5.

### RQ3. Does the choice of actual (first release or latest vintage) change the conclusions?

**6.4 Revision analysis of the sources**

- From the vintage store, for every (series, date) with more than one vintage: number of revisions, days from first to last vintage, absolute and relative size of the revision.
- Grid-India: re-uploads of the same day's report (the listing keeps the newest; the store keeps every version we fetched).
- CPCB: bulletins are usually not revised; measure how often a re-download has a different hash.
- Note that live vintages are fetch dates, so revisions that happen between two fetches are only seen once.
- Output: T7, F6.

**6.5 First release versus latest vintage scoring**

- Rescore all forecasts with the latest vintage as of the analysis date instead of the first release.
- Compare skill, ranks and coverage. Report the change and its bootstrap interval.
- If the change is inside the interval for every model, say so plainly.
- Output: T8.

### RQ4. How much does prospective evaluation differ from a static backtest on the same series and dates?

**6.6 Contamination argument**

- For each model, run a static backtest: same panel series, same 90 run dates, same horizons, same code, but run after the fact using the as-of history for each date (`VintageStore.as_of(run_date)`), so the inputs match the live inputs as closely as possible.
- Compare static and prospective scores per model, per run date. For deterministic models (seasonal naive, AutoETS, AutoARIMA, LightGBM with fixed seed) the two should match exactly if inputs match. Any difference measures input drift or non-determinism, not contamination.
- For the foundation models, the same weights are pinned (revision and SHA-256 in `run.json`), so with identical inputs the static run should also match. A match confirms the pipeline is reproducible.
- The contamination argument is therefore not "static scores are better". It is:
  1. Within the window, prospective scoring makes contamination impossible, because the targets did not exist at forecast time and the weights were pinned before launch.
  2. Separately, run a static backtest on the same series for an earlier period (2025-04-01 to 2026-10-26, which may be in pretraining corpora of models released after it) and compare each foundation model's skill on the earlier period with its prospective skill, relative to the baselines. A foundation model whose relative skill drops much more than the baselines' between the static and prospective periods is consistent with (not proof of) contamination or overfitting to public data.
- State what this cannot show: period effects (season, monsoon, festivals) also change skill. Use the baselines as the control for period effects.
- Output: T9, F7.

### RQ5. How reliable is a daily public arena in practice?

**6.7 Failure and gap statistics**

- Per source: share of run days skipped and why (from `health/source_health.csv`).
- Per model: share of run days with a successful forecast per source, timeouts, crashes, contract errors (from `run.json` `failures`).
- Values forward-filled in inputs (`prepared.json` `filled_values`) and series skipped for lag or short history.
- OpenTimestamps: share of forecast files with a stamp, and share upgraded to a Bitcoin attestation.
- Timing: for each run date, git commit time of the forecast file versus the publication time of the first target (horizon 1). This matters most for CPCB, whose bulletin for day D appears on the evening of day D.
- Output: T1, T10, F8.

**6.8 Compute cost per model**

- From `run.json`: `seconds` per model per source per run, on GitHub-hosted CPU runners.
- Report median and 90th percentile seconds per run and per series. Report weight size and peak memory if recorded (add peak memory logging before the window closes, or state it was not recorded).
- Plot skill against median seconds per run.
- Output: T11, F9.

### Optional, if time allows (labelled exploratory)

- Per-series results for the largest states and cities.
- Behaviour around known events in the window (Diwali, winter fog episodes, cold waves), described only, no causal claim.
- Results for any outside submissions, kept in a separate table and flagged with their training data statement.

## 7. Threats to validity

1. **Short window.** 90 days covers one season (late monsoon withdrawal to winter). AQI in north Indian cities is at its worst in this period and power demand is lower than summer. Results may not hold in summer or monsoon.
2. **Small panel.** Up to 37 series by the rules (2 national + 15 states + 20 cities), from two sources. Series are not independent (neighbouring states, cities in the Indo-Gangetic plain).
3. **Dependence in inference.** Overlapping horizons and cross-series correlation reduce the effective sample size. Bootstrap and DM intervals may be too narrow.
4. **Gap handling.** Inputs are forward-filled up to the cutoff. A series up to 2 days behind its source cutoff is filled with its last value. This favours persistence-like models and changes the MASE scale slightly.
5. **First-release definition.** Live vintages are fetch dates, not true publication times. If a source revises a value before our first fetch, we never see the original.
6. **Same-day publication for CPCB.** The CPCB bulletin for day D appears on the evening of day D. Scoring drops any row whose commit time is not before the end of the target's averaging window (16:00 IST for CPCB). Section 6.7 reports how many rows this removed and checks commit times against GitHub's push timestamps as an independent record.
7. **Model configuration.** Every model runs with one configuration chosen before launch, on CPU, with a 1,024-day context cap for foundation models and 730 days for baselines. Better configurations exist. Results are about these configurations, not the model families.
8. **Single maintainer.** The maintainer wrote the pipeline and chose the baselines. Hashing protects forecast integrity, not design choices. The design was written down before launch (docs/DECISIONS.md, config/panel_rules.yaml).
9. **Source changes.** Parser breaks (layout changes) cause skipped days that are not random. If a source breaks during an unusual period, results are biased.
10. **Licensing.** If either source refuses republication of derived values, the public data branch may have to change. The analysis would then rely on the maintainer's local store, which weakens outside verification.
11. **Non-determinism.** Seeds are fixed, but GPU-free PyTorch can still vary across library versions. Section 6.6 measures this.

## 8. Tables and figures

All outputs are written to `paper/` (not yet created). File names are fixed now so the scripts and text can refer to them.

### Tables (CSV plus a rendered Markdown or LaTeX copy)

| ID | File | Content |
|---|---|---|
| T1 | `paper/tables/t1_data_health.csv` | Per source: run days, healthy days, skips by reason, rejected files, forward-filled values |
| T2 | `paper/tables/t2_skill_overall.csv` | Per model: scaled CRPS skill, MASE skill, 95% intervals (run-date bootstrap and moving-block bootstrap), n scored, days live |
| T3 | `paper/tables/t3_skill_by_source_horizon.csv` | Skill and intervals per model, source and horizon bucket |
| T4 | `paper/tables/t4_dm_pairwise.csv` | Pairwise DM statistics with HAC variance and HLN correction |
| T5 | `paper/tables/t5_model_confidence_set.csv` | Models in the 90% MCS, overall and per source |
| T6 | `paper/tables/t6_coverage.csv` | Coverage of 20/40/60/80% intervals per model, source, horizon bucket |
| T7 | `paper/tables/t7_revisions.csv` | Revision counts and sizes per source |
| T8 | `paper/tables/t8_first_vs_latest.csv` | Skill under first-release and latest-vintage scoring, and the difference |
| T9 | `paper/tables/t9_static_vs_prospective.csv` | Static backtest (earlier period and same window) versus prospective skill |
| T10 | `paper/tables/t10_model_failures.csv` | Per model and source: successful runs, timeouts, crashes, invalid output |
| T11 | `paper/tables/t11_compute.csv` | Seconds per run (median, p90), seconds per series, weight size |

### Figures (PNG and SVG)

| ID | File | Content |
|---|---|---|
| F1 | `paper/figures/f1_skill_intervals.svg` | Scaled CRPS skill with 95% intervals per model, overall |
| F2 | `paper/figures/f2_skill_by_horizon.svg` | Skill against horizon 1 to 28, one line per model, faceted by source |
| F3 | `paper/figures/f3_pit_histograms.svg` | PIT histograms per model and source |
| F4 | `paper/figures/f4_reliability.svg` | Nominal versus observed coverage for 20/40/60/80% intervals |
| F5 | `paper/figures/f5_coverage_by_horizon.svg` | 80% coverage against horizon, per model |
| F6 | `paper/figures/f6_revisions.svg` | Distribution of revision sizes per source |
| F7 | `paper/figures/f7_static_vs_prospective.svg` | Relative skill in static and prospective periods, per model |
| F8 | `paper/figures/f8_gaps_timeline.svg` | Calendar of source health and model failures over the window |
| F9 | `paper/figures/f9_skill_vs_compute.svg` | Skill against median seconds per run |
| F10 | `paper/figures/f10_example_fans.svg` | Fan charts for two example series (one state, one city), chosen by a rule fixed now: the largest state and the first city in the panel |

Every figure title states its takeaway, computed from the data, in the same way the site does.

## 9. Reproducibility section

- Exact commit of `main` used for analysis; data branch commit used.
- `bhavishya verify` output showing every manifest hash matches.
- OpenTimestamps verification command and the share of proofs upgraded.
- Package versions and Hugging Face revisions for each model (from `run.json`).
- How to rerun every table: one command per table in `analysis/README.md`.

## 10. Limitations and future work

- Longer window (a full year) before any strong claim.
- Agmarknet mandi prices once a data.gov.in key is available.
- Covariates (Open-Meteo) for models that accept them, as a separate track.
- TimesFM 3.0 if its licence and packaging allow.
- Outside submissions, reported separately.

## 11. Checklist before submission

- [ ] Analysis scripts committed before running on the full window.
- [ ] Prior art rechecked within two weeks of submission.
- [ ] Every number in the text traced to a table file.
- [ ] Permission status for CPCB and Grid-India stated in the data section.
- [ ] Threats to validity reviewed by at least one outside reader.
