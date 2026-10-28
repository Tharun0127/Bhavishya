# DRAFT: Forecasting Indian public data before it exists

*Draft blog post by Tharun0127. Not published.*

Bhavishya (IndiaCast Arena) is a live forecasting arena for India. Every day it asks seven time series models to forecast Indian public data that has not been published yet, records the forecasts in a way that cannot be quietly changed, and scores them when the real numbers arrive. It started on 27 October 2026. There are no results yet. This post explains why it exists, how it works, what is not new about it, and where it is weak.

Leaderboard: https://tharun0127.github.io/Bhavishya/
Code: https://github.com/Tharun0127/Bhavishya

## The problem: static benchmarks and contamination

Most forecasting benchmarks are static. You take a public dataset, hold out the last part, and score models on it. This worked when models were trained per dataset. It works less well for time series foundation models, which are pretrained on large collections of public series. If a benchmark's test period, or a series closely correlated with it, is in the pretraining corpus, the score partly measures memory. Meyer et al. (arXiv 2510.13654) describe two forms of this: reuse of the same datasets in training and testing, and temporal overlap between correlated training and test series.

You can reduce the risk with fresh or private data. You cannot rule it out for a model released after the data was published. The one design that rules it out is to score forecasts of values that did not exist when the forecast was made. That is prospective evaluation.

## What the arena runs

Two Indian public sources are targets:

- **Grid-India daily Power Supply Position report.** Energy met per day, nationally and for the 15 states with the highest mean energy met, plus national maximum demand. Published the next morning.
- **CPCB daily AQI bulletin.** The National AQI for up to 20 large cities, a 24-hour value to 16:00 IST. Published the same evening.

The series were chosen by written rules before the first forecast. No rule looks at past forecast errors.

Seven models forecast every series 1 to 28 days ahead, as nine quantiles: seasonal naive (the reference), AutoETS, AutoARIMA, a global LightGBM with conformal intervals, and three zero-shot foundation models pinned to exact Hugging Face revisions: Chronos-2, TimesFM 2.5 (200M) and Moirai 2.0 small. TimesFM 3.0 is not included because of its non-commercial licence and because its code was not on PyPI at launch. Agmarknet mandi prices need a data.gov.in key and are deferred.

## Design

### Vintages

Sources revise data. Grid-India sometimes re-uploads a corrected report. If you overwrite old values, you cannot rebuild what a model could have known on a past date, and backtests leak.

The data store keeps every version of every value, keyed by the date it was known (its vintage). Two queries matter. `as_of(date)` returns the latest version known on that date, and it builds model inputs. `first_release()` returns the earliest version of each value, and it is what forecasts are scored against. Later revisions are kept for separate study, so scores do not drift after the fact.

The same loaders ship in the pip package, so anyone can fetch these sources with vintage-dated raw snapshots on their own machine.

### Hashed commits

Each day, all model outputs are merged into one forecast file. The arena computes its SHA-256, appends the hash to an append-only manifest, and pushes both to a public git branch. It also submits the hash to public OpenTimestamps calendars, which anchor it in the Bitcoin blockchain within a few hours. Before scoring, every file is checked against its manifest hash, and scoring refuses any mismatch.

If anyone, including me, changed a past forecast, the hash would no longer match the manifest, every clone or the timestamp proof. This is tamper evidence, not tamper prevention.

### First-release scoring

Each forecast is joined to the first published actual and to a MASE scale computed from the same history the models saw, saved at forecast time. Metrics are MASE on the median, CRPS approximated from the nine quantiles, scaled CRPS, and whether the 80% interval covered the actual.

Skill is the geometric mean over series of the ratio of a model's mean score to seasonal naive's, on forecasts both made. Intervals come from a bootstrap that resamples whole run dates, because errors on the same day are correlated. No model is ranked before 28 days live and 10,000 scored forecasts.

### Isolation

Each model runs in its own process and CI job, with read-only permissions, on an input file already truncated at the cutoff. The model interface also refuses history after the cutoff and checks the output. Outside submissions run in Docker with no network, a read-only filesystem and resource caps, and the host re-validates their output.

## What is not new

Live forecasting benchmarks for foundation models already exist:

- **TS-Arena** (KDD 2026) runs pre-registered live forecasts on energy data from Germany, the US and Finland. It is the closest prior work.
- **Impermanent** evaluates models live on GitHub activity series, with MASE and scaled CRPS.
- **LiveHouse-TS** is a living benchmark across 17 datasets from 15 public sources, scored with CRPS.

Live CRPS scoring is not new. Hash commit-reveal for forecasts is not new either (Foresight Arena does it for event forecasting). Foundation models have been evaluated on CPCB air quality data before, statically, in Air Quality Arena.

What I can claim is narrower. To my knowledge, this is the first open, prospective benchmark of time series foundation models on Indian public series where each forecast is hashed and committed to a public git repository with OpenTimestamps proofs before the outcome exists, paired with pip-installable loaders that keep vintage-dated snapshots of Grid-India and CPCB data. That claim rests on searches up to 27 October 2026. The full list is in `docs/PRIOR_ART.md`.

## Limitations

- **No results yet.** Rankings need the thresholds above.
- **Small and young.** Two sources, a few dozen series, one season so far.
- **One configuration per model, on CPU, no covariates.** Vendors could do better.
- **Gap handling.** Inputs are forward-filled up to the cutoff, which slightly favours persistence-like models. Filled values are counted.
- **CPCB same-day release.** The bulletin for day D appears that evening, so the horizon-1 CPCB forecast is prospective only if the daily commit lands first. I will check commit times against release times.
- **Dependent errors.** Overlapping horizons mean the run-date bootstrap may give intervals that are too narrow.
- **Licences.** I publish derived daily values, forecasts, scores and file hashes, not the original files, and I am asking CPCB and Grid-India for permission.

## How to submit a model

Copy `submissions/_template/`, implement `_predict(history, horizon)` returning nine quantiles per series and horizon, fill in `model.yaml` (including whether you trained on data after 27 October 2026), and download weights in the `Dockerfile`. Open a pull request. A maintainer reviews it and runs it once in the sandbox. After merge it runs daily, and days live count from its first committed forecast. CONTRIBUTING.md has the details.

If you think the method is wrong, open an issue. Scoring and panel changes apply only to new panel versions.
