# Interview prep: Bhavishya (IndiaCast Arena)

A component-by-component guide to the code, for explaining the project in technical interviews. Each section covers what the component does and why, the key code explained line by line, the five likeliest questions with answers, and weak points with honest responses. A glossary is at the end.

The arena launched on 2026-10-27. **There are no results yet.** If asked "which model wins?", the honest answer is "I do not know yet, and the system is built so that I cannot pretend to know early: no model is ranked before 28 days live and 10,000 scored forecasts."

## The project in 60 seconds

Bhavishya is a live forecasting arena for India. Every day, seven time series models (seasonal naive, AutoETS, AutoARIMA, LightGBM, Chronos-2, TimesFM 2.5 and Moirai 2.0 small) forecast Indian public data 1 to 28 days ahead: daily energy met per state from Grid-India, and daily city AQI from CPCB. The forecasts are written to one file, SHA-256 hashed, added to an append-only manifest, committed to a public git branch and timestamped with OpenTimestamps, all before the outcomes exist. When the actual values are published, the arena scores each forecast against the first-released value using MASE, quantile CRPS and 80% interval coverage, and reports skill relative to seasonal naive with block bootstrap intervals over run dates.

Why: static benchmarks reuse public datasets that may be in a foundation model's training data. A prospective benchmark cannot be contaminated in the evaluation window, because the targets did not exist when the forecast was made.

What is not new: live TSFM benchmarks already exist (TS-Arena, Impermanent, LiveHouse-TS). The narrower claim is prospective, hash-committed evaluation on Indian public series, plus vintage-aware loaders (docs/PRIOR_ART.md section 6).

## Architecture map

```
sources/*.py  --list_files, parse-->  fetch.py  --validate-->  contracts.py
                                          |
                                          v
                                      store.py (VintageStore: raw + observations per vintage)
                                          |
arena/daily.py: fetch_live -> health.judge -> prepare (as_of, truncate, regularise, MASE scales)
                -> run_model (one subprocess per model, models/run.py) -> commit_forecasts
                -> hashing.append_manifest + ots_stamp -> git push (daily.yml)
                                          |
arena/scoring.py: load_committed (verify hashes) -> first_release actuals -> score_frame
                                          |
arena/leaderboard.py: paired -> geometric mean ratio -> block bootstrap -> leaderboard
                                          |
arena/site.py: static HTML pages (leaderboard, series, data, status)
```

---

## 1. Data loaders and data contracts

Files: `src/bhavishya/sources/base.py`, `sources/grid_india.py`, `sources/cpcb_aqi.py`, `sources/open_meteo.py`, `src/bhavishya/contracts.py`, `src/bhavishya/http.py`.

### What it does and why

Each source is a class with two jobs: list the files that cover a date range, and parse one file into a tidy frame with six fixed columns. A contract then checks schema, units, value ranges, duplicates and timestamps before anything downstream sees the data. Government sites change layouts without notice. A contract turns a silent parse error into a loud, recorded skip.

Three sources ship. Grid-India (XLS from a keyless JSON listing API) and CPCB (one PDF per day, URL is a function of the date) are arena targets. Open-Meteo is covariates only, because its values are model output and revise freely.

### Key code

The interface (`sources/base.py`):

```python
class Source(ABC):
    info: SourceInfo
    contract: Contract

    @abstractmethod
    def list_files(self, client: PoliteClient, start: pd.Timestamp, end: pd.Timestamp) -> list[FileRef]:

    @abstractmethod
    def parse(self, content: bytes, ref: FileRef, vintage_date: pd.Timestamp) -> pd.DataFrame:
```

- `class Source(ABC)`: an abstract base class. You cannot instantiate a source that does not implement both methods.
- `info: SourceInfo`: human facts (publisher, licence, attribution, release lag) used on the site and in docs.
- `contract: Contract`: the rules this source's data must pass.
- `list_files(...)`: returns `FileRef` objects (URL, filename, observation date, publication date). Listing is separate from downloading, so fetch logic is shared.
- `parse(content, ref, vintage_date)`: bytes in, tidy frame out. The vintage date is passed in, because the caller decides what vintage means (fetch date or publication date).

CPCB listing (`sources/cpcb_aqi.py`):

```python
return [
    FileRef(
        url=BULLETIN_URL.format(ymd=day.strftime("%Y%m%d")),
        filename=f"AQI_Bulletin_{day:%Y%m%d}.pdf",
        obs_date=day,
        published=day,
    )
    for day in pd.date_range(start, end, freq="D")
]
```

- There is no listing API, so one `FileRef` is built per day.
- `url=...`: the bulletin URL is a pure function of the date.
- `obs_date=day`: the bulletin describes this day.
- `published=day`: the bulletin for day D is published on the evening of day D. This becomes the vintage for backfills.
- Missing days come back as 404, which `Source.download` turns into `None`.

Row parsing (`sources/cpcb_aqi.py`):

```python
cells = [(c or "").replace("\n", " ").strip() for c in row]
if len(cells) < 4 or not _INT.match(cells[0]) or not _INT.match(cells[3]):
    return None
city = slugify(cells[1])
return (city, float(cells[3])) if city else None
```

- Line 1: PDF table cells can be `None` or contain line breaks; normalise them.
- Line 2: a data row starts with an integer serial number and has an integer AQI in column 4. Header rows and notes fail this check and are skipped.
- Line 4: city names become stable ASCII slugs (`"J&K(UT) & Ladakh"` becomes `j_k_ut_ladakh`).
- Line 5: return the city and its AQI, or nothing.

Grid-India re-uploads (`sources/grid_india.py`):

```python
prev = refs.get(ref.obs_date)
if prev is None or _release_key(ref) >= _release_key(prev):
    refs[ref.obs_date] = ref
```

- The listing can contain more than one file for the same day (a corrected re-upload).
- Keep the one with the latest publication date. Earlier versions we already fetched stay in the store as separate vintages.

The contract check (`contracts.py`):

```python
def validate(self, df: pd.DataFrame) -> pd.DataFrame:
    problems = check_schema(df)
    if problems:
        raise ContractError(self.source, problems)
    problems += self._check_values(df)
    if problems:
        raise ContractError(self.source, problems)
    return df
```

- Schema first: exact column order and dtypes. If the schema is wrong, value checks would crash, so stop early.
- Then values: correct source, series prefix, known units, no NaN, values inside unit ranges, no duplicate keys, daily timestamps at midnight.
- `ContractError` carries the full list of problems, so the health log says exactly what broke.

One value check worth explaining:

```python
if self.frequency == "D" and (df["timestamp"] != df["timestamp"].dt.normalize()).any():
    problems.append("daily timestamps not at midnight")
```

- For daily data, a timestamp that is not midnight means a timezone or parsing bug. Catching it here prevents off-by-one-day joins later.

The polite HTTP client (`http.py`):

```python
elapsed = time.monotonic() - self._last_call.get(host, 0.0)
if elapsed < self.min_interval:
    time.sleep(self.min_interval - elapsed)
self._last_call[host] = time.monotonic()
```

- At most one request per second per host, with retries and backoff on 429 and 5xx, and an honest User-Agent with the repo URL. Government servers are small.

### Likely questions

1. **Why a contract instead of just try/except around the parser?**
   A parser can succeed and still return wrong data: a shifted column gives plausible-looking numbers. The contract checks meaning (units, ranges, row counts), not just "did it crash". The `min_rows_per_file` rule (50 cities for CPCB, 20 rows for Grid-India) catches the most common silent failure: a layout change that makes the parser find only a few rows.

2. **Why is Open-Meteo not a target?**
   Its values are reanalysis and forecast blends, not observations, and they are revised freely. Scoring a model against another model's output does not measure forecasting skill against reality. It is useful as covariates.

3. **How do you handle state names changing?**
   A new name becomes a new series id. The panel is fixed, so a renamed state would show up as a lagging series and be skipped, and the health log would show it. Mapping old to new names is manual on purpose, so it is visible.

4. **Why PDFs for CPCB when there is an API?**
   The data.gov.in CPCB API needs a key and gives real-time station values only, with no history. The bulletin is keyless, has history back to at least 2023, and is the official daily city figure.

5. **How would you add a new source?**
   Subclass `Source`, implement `list_files` and `parse` returning `make_tidy(...)`, define a `Contract`, record fixtures for tests, add it to `SOURCES`, and document its licence in DATA_SOURCES.md. Only add it to `TARGET_SOURCES` if it is an official record that revises rarely.

### Weak points and honest responses

- **PDF parsing is fragile.** True. pdfplumber table extraction depends on layout. The contract makes failures loud, and the health job opens an issue, but a layout change still means lost days until the parser is fixed.
- **`published=day` for CPCB is an assumption.** The PDF does not carry a machine-readable release time. I use the documented release pattern. For live data the vintage is the fetch date anyway, which is conservative.
- **Grid-India terms are unverified.** Its copyright page did not load. I publish derived values only, with attribution and file hashes, and have drafted a permission request.

---

## 2. Vintage store

File: `src/bhavishya/store.py`.

### What it does and why

Sources revise history. The store keeps every version of every value, keyed by the date it was known (the vintage). This answers two questions exactly: what data existed on day D (to build inputs with no future information), and what was the first published value (to score against).

Layout: raw bytes per source and vintage, tidy rows in `observations/<source>/<vintage>.parquet`, and an append-only `raw_index.csv` with the SHA-256 of every downloaded file.

### Key code

```python
def as_of(self, as_of: pd.Timestamp, sources: list[str] | None = None) -> pd.DataFrame:
    obs = self.observations(sources, as_of)
    obs = obs.sort_values("vintage_date").drop_duplicates(["series_id", "timestamp"], keep="last")
    return obs.sort_values(["series_id", "timestamp"]).reset_index(drop=True)
```

- Line 2: load every row with `vintage_date <= as_of`. Rows from later vintages are never read.
- Line 3: sort by vintage and keep the last row per (series, date): the latest version known on that day.
- Line 4: return in a stable order.

```python
def first_release(self, sources: list[str] | None = None) -> pd.DataFrame:
    obs = self.observations(sources)
    obs = obs.sort_values("vintage_date").drop_duplicates(["series_id", "timestamp"], keep="first")
```

- Same idea with `keep="first"`: the earliest version of each value. Scoring uses this.

```python
for f in sorted(src_dir.glob("*.parquet")):
    if as_of is not None and pd.Timestamp(f.stem) > as_of:
        continue  # file name is the vintage, so we can skip without reading
```

- The file name is the vintage date, so later vintages are skipped without opening the file. This is both faster and a structural guarantee that future rows are not loaded.

```python
part = part.drop_duplicates(["series_id", "timestamp"], keep="last")
```

- In `save_observations`: saving the same rows twice is a no-op, so re-running a fetch is safe.

### Likely questions

1. **Why not just overwrite values when a source revises?**
   Then you cannot reconstruct what a model could have known on a past date, and backtests would leak revised values. You also could not study revisions.

2. **Why score against the first release and not the final value?**
   The first release is what existed when the outcome first became public. Scoring against later revisions mixes forecast error with revision noise and lets scores drift after the fact. Revisions are kept, so latest-vintage scoring can be run as a secondary analysis.

3. **What is the vintage for live data versus backfill?**
   Live: the date we fetched it (IST). Backfill: the source's own publication date, because that is when the data existed publicly. Backfilled raw files go in `raw_backfill/` and are not published.

4. **Why parquet per vintage and not a database?**
   It lives on a git branch, is easy to diff and verify, needs no server, and the file name doubles as an index. The data is small (tens of series, daily).

5. **How do you detect a revision?**
   `fetch.py` computes the SHA-256 of each download. Identical bytes are skipped. Different bytes for the same day produce new rows under a new vintage. Comparing first and later vintages per (series, date) gives the revision.

### Weak points and honest responses

- **Live vintage is fetch date, not true publication time.** If a source revises before our first fetch, we never see the original. A daily fetch keeps this window to about a day.
- **`observations()` reads every file each time.** Fine at this size. With years of data I would add a partitioned dataset or DuckDB.
- **The as-of view is date-granular.** It cannot express "published at 18:00". Scoring does not rely on it for timing: it compares the commit time with the instant each target period ends at the source (see the scoring section).

---

## 3. Fetch pipeline

File: `src/bhavishya/fetch.py`.

### What it does and why

Downloads every file for a source and date range, snapshots the raw bytes, parses, validates against the contract, and saves tidy rows. It never raises for a single bad file. It returns a `FetchResult` listing good files, missing files, download errors and contract errors, so the health check can decide whether the source is usable today.

### Key code

```python
vintage = (ref.published or today_ist()) if backfill else today_ist()
```

- Backfill: use the source's publication date if known. Live: use today's IST date, because that is when we saw the data.

```python
digest = sha256_bytes(content)
if digest in known:
    return None  # identical bytes already stored: not a new vintage
```

- The live fetch looks back 10 days every run to catch re-uploads. Files whose bytes we already have are ignored, so only real changes create new vintages.

```python
try:
    frame = source.parse(content, ref, vintage)
    source.contract.validate(frame)
except ContractError as exc:
    result.contract_errors.append(f"{ref.filename}: {exc}")
    frame = None
except Exception as exc:
    result.contract_errors.append(f"{ref.filename}: parse failed: {exc!r}")
    frame = None
```

- Parse and validate in one block. Contract violations and parser crashes are both recorded as contract errors and the frame is dropped.

```python
store.save_raw(source.name, vintage, ref.filename, content, backfill)
status = "ok" if frame is not None else "rejected"
store.log_fetch({... "sha256": digest, ... "status": status})
```

- The raw file is saved and logged even if rejected, so a rejected file can be inspected later. Only accepted frames are saved as observations.

### Likely questions

1. **Why look back 10 days on every live fetch?** To catch late uploads and corrected re-uploads. Hash de-duplication makes the repeat cheap.
2. **Why save rejected raw files?** To debug layout changes and to prove what the source served on that day.
3. **What happens if the listing call fails?** The whole source gets a `listing failed` error, the health check marks it `failed`, and the source is skipped for the day.
4. **Why `today_ist()` and not UTC?** All sources publish on Indian calendar dates. A UTC date would be the previous day for most of the IST morning, which would shift vintages.
5. **How is this tested?** With recorded fixtures of real files, so tests do not hit government servers.

### Weak points and honest responses

- **Rejected files are logged with `status=rejected` but `known_hashes` only includes `ok`.** So a rejected file is retried on every run for 10 days. That is deliberate (a parser fix will pick it up), but it costs some repeat downloads.
- **Sequential downloads.** One request per second per host. Fine for daily runs, slow for long backfills, and that is the polite choice.

---

## 4. Model interface and leakage guard

Files: `src/bhavishya/models/base.py`, `models/run.py`, `models/registry.py`.

### What it does and why

Every model, built-in or submitted, implements one method: `_predict(history, horizon)` returning nine quantiles per series and horizon. The base class wraps it with input checks (no data after the cutoff), a history length cap, and output checks (exact row set, finite values, sorted quantiles). Models run in their own process and only see a file that was already truncated at the cutoff.

### Key code

```python
QUANTILES: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
HORIZON = 28
```

- Nine quantile levels and a 28-day horizon, fixed for all models so scores are comparable.

```python
def check_no_leakage(history: pd.DataFrame, cutoff: pd.Timestamp) -> None:
    latest = history["timestamp"].max()
    if pd.notna(latest) and latest > cutoff:
        raise LeakageError(f"history reaches {latest:%Y-%m-%d}, after cutoff {cutoff:%Y-%m-%d}")
```

- Find the newest timestamp the model was given. If it is after the cutoff, refuse to run. This is a second line of defence: the input file is already truncated.

```python
def forecast(self, history, cutoff, horizon=HORIZON):
    check_no_leakage(history, cutoff)
    start = cutoff - pd.Timedelta(days=self.max_history_days - 1)
    hist = history.loc[history["timestamp"] >= start, list(HISTORY_COLUMNS)].copy()
    raw = self._predict(hist, horizon)
    return finalize_forecast(raw, cutoff, horizon, sorted(hist["series_id"].unique()))
```

- Line 2: leakage check.
- Lines 3 to 4: cap history length per model (1,024 days for foundation models, 730 for baselines) and keep only the three model columns, so a model never sees units, sources or vintages.
- Line 5: call the subclass.
- Line 6: validate and label the output. Subclasses cannot skip this.

```python
expected = {(s, h) for s in expected_series for h in range(1, horizon + 1)}
got = set(zip(out["series_id"], out["horizon"], strict=True))
if got != expected or len(out) != len(expected):
    raise ValueError(...)
values = out[list(QUANTILE_COLUMNS)].to_numpy(dtype="float64")
if not np.isfinite(values).all():
    raise ValueError("model returned non-finite quantiles")
out[list(QUANTILE_COLUMNS)] = np.sort(values, axis=1)
```

- Lines 1 to 4: exactly one row per series and horizon, no extras, no gaps, no duplicates.
- Lines 5 to 7: no NaN or infinity.
- Line 8: sort the quantiles in each row. This fixes quantile crossing without inventing new values.

```python
out["cutoff"] = pd.Timestamp(cutoff)
out["target_date"] = out["cutoff"] + pd.to_timedelta(out["horizon"], unit="D")
```

- Target dates are computed by trusted code from the cutoff, never taken from the model.

```python
def config_hash(self) -> str:
    blob = json.dumps(self.config, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]
```

- A short hash of the model configuration, stored with each run, so a silent config change is visible.

The worker (`models/run.py`) loads the history file, times `model.forecast`, writes forecasts and an info JSON (versions, weights revision and hash, config hash, seconds, series count).

### Likely questions

1. **Why both truncation and a runtime check?** Defence in depth. Truncation happens in the arena before the file is written. The check protects against a bug in truncation or a model being run on the wrong file.
2. **Why a separate process per model?** Dependency conflicts (Moirai pins old torch and numpy), crash isolation, a hard timeout, and the process boundary means a model has no reference to the store or the run date.
3. **Why sort quantiles instead of rejecting crossed ones?** Crossing is common in quantile heads and is a presentation problem, not a leakage problem. Sorting keeps the same set of values and makes the forecast a valid distribution. It is applied equally to all models.
4. **Why nine quantiles and not samples?** All three foundation models output quantiles natively, the statistical models give intervals that map to quantiles, and nine quantiles give a standard CRPS approximation.
5. **Why not let models use covariates?** Simplicity and fairness at launch: every model gets the same univariate history. Covariates are planned as a separate track.

### Weak points and honest responses

- **The leakage guard checks timestamps, not vintages.** It assumes the input history is an as-of view. That is guaranteed by `prepare`, not by the model interface.
- **A model running in the main environment could in principle import the store.** Built-in models are trusted code from `main`. Submissions run in Docker with no network and only the history file mounted.
- **Fixed 28-day horizon for every series.** A real user of AQI forecasts cares most about 1 to 3 days. The horizon buckets in scoring make short horizons visible.

---

## 5. Baselines

File: `src/bhavishya/models/baselines.py`.

### What it does and why

Four non-foundation models: seasonal naive, AutoETS and AutoARIMA (statsforecast, one model per series), and a global LightGBM (mlforecast) with conformal prediction intervals. Seasonal naive is the reference model all skill scores divide by. Strong, cheap baselines are the point: a foundation model that does not beat AutoETS on daily power data is not useful for this task.

### Key code

```python
SEASON = 7  # weekly seasonality: the dominant pattern in daily power demand and AQI
```

- Weekly cycle: weekday versus weekend demand, and weekly traffic and activity patterns in AQI.

```python
sf = StatsForecast(models=[self._make()], freq="D", n_jobs=1)
fc = sf.forecast(df=to_nixtla(history), h=horizon, level=list(LEVELS))
fc = fc.reset_index() if "unique_id" not in fc.columns else fc
return add_horizon(intervals_to_quantiles(fc, self.model_col))
```

- Line 1: one statsforecast model, daily frequency, single core (CI runners are shared).
- Line 2: rename columns to Nixtla's `unique_id, ds, y`, forecast `h` days, and ask for central intervals at 20, 40, 60, 80%.
- Line 3: older statsforecast versions put `unique_id` in the index; handle both.
- Line 4: convert intervals to quantiles and number the horizons.

```python
for level in LEVELS:
    lo_q = round((1 - level / 100) / 2, 1)
    hi_q = round((1 + level / 100) / 2, 1)
```

- A central L% interval has endpoints at quantiles (1 - L/100)/2 and (1 + L/100)/2. Levels 20, 40, 60, 80 give quantiles 0.4/0.6, 0.3/0.7, 0.2/0.8, 0.1/0.9. The median is the point forecast. That is all nine.

LightGBM:

```python
mlf = MLForecast(
    models={"LGBM": LGBMRegressor(**self.params)},
    freq="D",
    lags=[1, 7, 14, 21, 28],
    lag_transforms={1: [RollingMean(window_size=7), RollingMean(window_size=28)]},
    date_features=["dayofweek", "month"],
    target_transforms=[LocalStandardScaler()],
)
mlf.fit(to_nixtla(history), prediction_intervals=PredictionIntervals(n_windows=3, h=horizon))
fc = mlf.predict(horizon, level=list(LEVELS))
```

- One model across all series of a source (a global model).
- Lags at weekly multiples plus lag 1; rolling means of lag 1 over a week and four weeks; day of week and month as features.
- `LocalStandardScaler`: standardise each series, so large and small states can share one model.
- `PredictionIntervals(n_windows=3, h=horizon)`: conformal intervals from the errors on the last three 28-day windows of history.
- Prediction is recursive: each step's prediction feeds the next step's lag 1.

### Likely questions

1. **Why seasonal naive as the reference?** It is the standard scale-free reference in forecasting (MASE uses it), it is hard to beat at short horizons on strongly weekly data, and a skill ratio below 1 has a plain meaning.
2. **Why are the intervals for statistical models trustworthy?** They are model-based (ETS and ARIMA assume Gaussian errors). They may be too narrow if the model is wrong. That is exactly what the coverage metric measures.
3. **What does conformal add for LightGBM?** LightGBM gives point forecasts. Conformal calibration turns past out-of-sample errors into intervals with a coverage guarantee under exchangeability, without assuming a distribution.
4. **Why 730 days of history for baselines?** Enough for yearly patterns, short enough to keep AutoARIMA fast on CI runners.
5. **Why no hyperparameter tuning?** Every model gets one configuration fixed before launch. Tuning on the evaluation period would be leakage. Outside contributors can submit better configurations.

### Weak points and honest responses

- **Only weekly seasonality.** Yearly and festival effects are left to the models' trend handling. MSTL or holiday features could help.
- **Conformal with three windows is a small calibration set.** 3 windows of 28 horizons per series. Coverage may be noisy. The arena will show it.
- **Exchangeability is violated in time series.** Conformal guarantees are approximate here. I would say so.

---

## 6. Foundation model wrappers

File: `src/bhavishya/models/foundation.py`.

### What it does and why

Wrappers for three zero-shot time series foundation models, each pinned to an exact Hugging Face commit. The SHA-256 of the weights file is computed on every run and stored with the forecasts. Each wrapper converts history to the model's input format and its output to the nine quantile columns.

### Key code

```python
CHRONOS2_REPO, CHRONOS2_REV = "amazon/chronos-2", "29ec3766d36d6f73f0696f85560a422f50e8498c"
TIMESFM_REPO, TIMESFM_REV = "google/timesfm-2.5-200m-pytorch", "1d952420fba87f3c6dee4f240de0f1a0fbc790e3"
MOIRAI2_REPO, MOIRAI2_REV = "Salesforce/moirai-2.0-R-small", "30f43ff08c8494f4943ae1521e9d4e94a0fbb389"
CONTEXT = 1024
```

- Exact commit hashes, not branch names, so weights cannot change under us.
- 1,024 days of context for every foundation model.

```python
def __init__(self) -> None:
    self._path, self._sha = hf_weights(CHRONOS2_REPO, CHRONOS2_REV)
```

- Download (or use the cache) at the pinned revision and hash the weights file. The hash goes into `ModelInfo.weights_sha256`.

Chronos-2:

```python
torch.manual_seed(0)
pipe = Chronos2Pipeline.from_pretrained(CHRONOS2_REPO, revision=CHRONOS2_REV, device_map="cpu")
df = history.rename(columns={"series_id": "item_id", "value": "target"})
fc = pipe.predict_df(df, prediction_length=horizon, quantile_levels=list(QUANTILES), ...)
```

- Fixed seed, CPU only, pinned revision.
- `predict_df` takes a long frame and returns one column per quantile level.
- Config records `cross_learning: False`: each series is forecast on its own.

TimesFM 2.5:

```python
model.compile(timesfm.ForecastConfig(max_context=CONTEXT, max_horizon=128,
    normalize_inputs=True, use_continuous_quantile_head=True, fix_quantile_crossing=True))
ids, arrays = _series_arrays(history)
_, q = model.forecast(horizon=horizon, inputs=arrays)
# TimesFM returns [mean, q0.1, ..., q0.9] in the last axis.
return _stack(ids, np.asarray(q)[:, :, 1:10], horizon)
```

- Compile with the context cap, input normalisation and the continuous quantile head.
- Pass one numpy array per series.
- The quantile output has 10 values per step: the mean first, then q0.1 to q0.9. Slice `1:10` to get the nine quantiles.

Moirai 2.0:

```python
pred = model.predict(past_target=[a[:, None] for a in arrays])  # (n, 9, horizon)
return _stack(ids, np.transpose(np.asarray(pred), (0, 2, 1)), horizon)
```

- Moirai wants each series as a 2D array (time by 1 dimension).
- It returns (series, quantile, horizon). Transpose to (series, horizon, quantile) to match the other wrappers.
- Moirai runs in its own virtual environment because `uni2ts` pins `torch<2.5`, `numpy~=1.26` and `scipy~=1.11` (docs/DECISIONS.md D4).

### Likely questions

1. **Why not TimesFM 3.0?** At launch its licence was non-commercial and its code was not on PyPI. The arena only runs models that can be installed reproducibly and whose forecasts can be published.
2. **How do you know the weights did not change?** The revision is a commit hash, and the file's SHA-256 is recorded on every run. A change would show up in `run.json`.
3. **Why CPU only?** GitHub-hosted runners are CPU. All three models are small enough. It also keeps the setup reproducible for anyone.
4. **Is this a fair comparison? The vendors could configure their models better.** Probably they could. These are reasonable default configurations, fixed before launch. The outreach drafts invite each team to submit an improved configuration through the normal submission process.
5. **Could these models have seen this data in pretraining?** Possibly, for the historical part. That is the reason for prospective scoring: the scored values did not exist when the weights were pinned.

### Weak points and honest responses

- **Model loading on every run.** Each run reloads the model. Fine for one run a day; a cache would help locally.
- **`hf_weights` assumes `model.safetensors`.** If a repo names its weights differently, the wrapper fails at init and the run is recorded as a failure. It would be caught on the first run.
- **No covariates.** Chronos-2 supports covariates and cross-series learning. Turning those off may understate it. This is a configuration choice that should be revisited with the vendor's input.

---

## 7. Daily cycle

File: `src/bhavishya/arena/daily.py`.

### What it does and why

One run per day: fetch recent files, judge each source's health, prepare model inputs as of the run date, run each model in a subprocess with a timeout, then merge, hash and commit forecasts. In CI, these steps are separate jobs (daily.yml).

### Key code

`prepare`, the core of leakage prevention:

```python
obs = store.as_of(run_date, [source])
obs = obs[obs["series_id"].isin(panel.for_source(source)) & (obs["timestamp"] <= run_date)]
cutoff = pd.Timestamp(obs["timestamp"].max())
```

- Line 1: only data with vintage on or before the run date.
- Line 2: only panel series, and no timestamps after the run date.
- Line 3: the cutoff for the whole source is the newest date any panel series has. All series in a source share a cutoff.

```python
elif (cutoff - last[sid]).days > MAX_SERIES_LAG_DAYS:
    prep.skipped_series[sid] = f"last value {last[sid]:%Y-%m-%d}, cutoff {cutoff:%Y-%m-%d}"
elif (cutoff - first[sid]).days + 1 < MIN_HISTORY_DAYS:
    prep.skipped_series[sid] = "history shorter than 90 days"
```

- Skip a series more than 2 days behind the source cutoff, or with under 90 days of history. Every skip is recorded with its reason.

```python
def regularise(history, cutoff):
    for sid, part in history.groupby("series_id", sort=True):
        idx = pd.date_range(part["timestamp"].min(), cutoff, freq="D")
        s = part.set_index("timestamp")["value"].reindex(idx)
        filled += int(s.isna().sum())
        frames.append(pd.DataFrame({"series_id": sid, "timestamp": idx, "value": s.ffill().to_numpy()}))
```

- Build a complete daily grid from each series' first date to the cutoff.
- Count the gaps, then forward-fill. Forward fill uses no future data. The count is stored in `prepared.json`.

```python
def mase_scales(history):
    def scale(values):
        return float(values.diff(SEASON).abs().mean())
```

- The MASE denominator: mean absolute 7-day difference of the input history. It is computed and saved at forecast time, from the same history the models saw, so it cannot depend on outcomes.

`run_model`:

```python
res = subprocess.run(cmd, capture_output=True, text=True, timeout=spec.timeout_s)
ok = res.returncode == 0
status[source] = "ok" if ok else f"exit {res.returncode}: {res.stderr.strip()[-500:]}"
```

- Run the worker in the model's own Python, with a timeout (30 minutes by default). Record `ok`, the exit code with the last 500 characters of stderr, or a timeout.

`commit_forecasts`:

```python
if path.exists():
    raise FileExistsError(f"{path} exists; forecasts are never overwritten")
...
"input_sha256": {p.name: sha256_file(p) for p in sorted(inputs.glob("*.parquet"))},
"forecasts_sha256": sha256_file(path),
...
append_manifest(store.root, {...})
if stamp:
    ots_stamp(path)
```

- Never overwrite a forecast file.
- `run.json` records the hash of every input file and of the forecast file, plus model info and failures.
- Append the forecast hash to the manifest, then request an OpenTimestamps stamp.

```python
for name in models or list(MODELS):
    try:
        run_model(store, MODELS[name], run_date)
    except Exception:  # a broken model must not stop the others
        log.exception("model %s failed before running", name)
```

- One broken model never stops the run.

### Likely questions

1. **How is the cutoff chosen?** Per source, the newest observation date available as of the run date. For Grid-India at 11:15 IST, that is usually the previous day.
2. **Why forward fill and not interpolation?** Interpolation uses the next value, which is future data relative to the gap. Forward fill does not.
3. **Why save MASE scales at forecast time?** So the scale is fixed before the outcome and cannot be tuned afterwards. It also documents exactly what history the scale came from.
4. **What happens if every model fails?** No forecast file is written, an error is logged, and the day is a gap for all models.
5. **What stops someone running the commit twice?** The file-exists check and the manifest refuses a path already listed. The CI `concurrency` group allows one writer at a time.

### Weak points and honest responses

- **Forward fill fabricates up to 2 days at the end of lagging series.** That favours persistence-like models slightly and is recorded in `filled_values`. A missing-aware input would be cleaner but not every model supports it.
- **CPCB horizon 1 timing (found during review, fixed).** The CPCB bulletin for day D is published on the evening of day D, so a date-only check could not tell whether a commit came before it. Scoring now compares the manifest commit time with the earliest instant the target can exist: 16:00 IST on the target date for CPCB (end of its 24-hour window) and midnight after it for Grid-India (`is_prospective` in scoring.py, tested in tests/test_scoring.py). A late run loses its CPCB horizon-1 rows automatically. Honest answer in an interview: the first version compared dates only; a review caught it before launch.
- **The live prospective check is weak by construction.** Live vintages are fetch dates, which are always after the run date. The check mainly guards backfill and bugs.

---

## 8. Hashing and OpenTimestamps

File: `src/bhavishya/arena/hashing.py`.

### What it does and why

Makes it detectable if anyone, including the maintainer, changes a forecast after the outcome is known. Three layers: SHA-256 of each forecast file in an append-only manifest; the manifest and file committed and pushed to a public git branch before outcomes exist; an OpenTimestamps proof anchoring the file hash in the Bitcoin blockchain via public calendars.

### Key code

```python
def append_manifest(root: Path, row: dict[str, object]) -> None:
    path = root / "manifest.csv"
    new = not path.exists()
    if not new and str(row["path"]) in set(read_manifest(root)["path"]):
        raise FileExistsError(f"{row['path']} is already in the manifest; forecasts are append-only")
    with path.open("a", newline="", encoding="utf-8") as fh:
```

- Refuse to add a second line for the same file. Open in append mode only.

```python
def verify_manifest(root: Path) -> list[str]:
    for row in read_manifest(root).itertuples():
        path = root / str(row.path)
        if not path.exists():
            problems.append(f"{row.path}: missing")
        elif sha256_file(path) != row.sha256:
            problems.append(f"{row.path}: hash mismatch")
```

- Recompute every hash. `bhavishya verify` runs this before every scoring job, and scoring itself refuses a mismatched file.

```python
with path.open("rb") as fh:
    detached = DetachedTimestampFile.from_fd(OpSHA256(), fh)
tip = detached.timestamp.ops.add(OpAppend(os.urandom(16))).ops.add(OpSHA256())
for url in calendars:
    try:
        tip.merge(RemoteCalendar(url).submit(tip.msg, timeout=30))
        stamped += 1
    except Exception:
        continue
```

- Line 2: hash the file.
- Line 3: append a random 16-byte nonce and hash again. The calendar receives this value, not the file hash, so it learns nothing about the file.
- Lines 4 to 9: submit to two public calendars. One success is enough. Failure never blocks the commit.

```python
if isinstance(att, PendingAttestation) and att.uri in CALENDARS:
    ts.merge(RemoteCalendar(att.uri).get_timestamp(ts.msg, timeout=30))
```

- `ots_upgrade`: hours later, ask the calendars for the Bitcoin attestation. Only calendars on our own list are contacted, even though the URI comes from the proof file.

### Likely questions

1. **Is git alone not enough?** Git history can be rewritten with a force push. Clones and forks make that detectable, and OpenTimestamps gives an independent time anchor that does not depend on GitHub.
2. **Why the nonce?** Privacy. The calendar should not learn the file hash. It is standard OpenTimestamps practice.
3. **Why use the library and not the `ots` command?** The command needs OpenSSL through ctypes and fails on Windows. The proof format is the same, so `ots verify` works on the result.
4. **What does the proof actually prove?** That the file's hash existed at or before the Bitcoin block time. Combined with the outcome's publication time, it shows the forecast came first.
5. **Could you just not publish a bad forecast?** Every run's file is committed, including all models, and `run.json` lists failures. Missing days show up as gaps in the manifest and the status page.

### Weak points and honest responses

- **The proof is pending for a few hours.** Until the Bitcoin attestation exists, the git commit time on GitHub is the main evidence.
- **The bot that commits could in principle commit different content.** It runs only trusted code from `main`, and the hash is computed in the same job that writes the file. A malicious maintainer could change code before a run; that is visible in `main`'s history.
- **Branch protection on `data` is a manual setting.** It is a launch checklist item.

---

## 9. Scoring metrics

File: `src/bhavishya/arena/scoring.py`.

### What it does and why

Joins every committed forecast with its first-released actual and the MASE scale saved at forecast time, and computes per-forecast metrics: absolute error of the median, MASE, CRPS (quantile approximation), scaled CRPS, and whether the 80% interval covered the actual.

### Key code

```python
def pinball(y, q, tau):
    diff = y[:, None] - q
    return np.maximum(tau * diff, (tau - 1.0) * diff)
```

- `y` has one actual per row; `q` has nine quantiles per row; `tau` the nine levels.
- If the actual is above the quantile (diff positive), loss is `tau * diff`. If below, loss is `(1 - tau) * |diff|`. Under-predicting a high quantile costs more than over-predicting it.

```python
def crps_from_quantiles(y, q, tau=TAUS):
    return 2.0 * pinball(y, q, tau).mean(axis=1)
```

- CRPS equals twice the integral of the pinball loss over all levels. With nine evenly spaced levels, twice the average pinball loss is the standard discrete approximation.

```python
df["prospective"] = df["actual_vintage"] > df["run_date"]
```

- An actual first published on or before the run date would mean the forecast was not prospective. Such rows are dropped and counted.

```python
scale = np.where(scale > 0, scale, np.nan)
df["abs_error"] = np.abs(y - df["q0.5"].to_numpy())
df["mase"] = df["abs_error"] / scale
df["crps"] = crps_from_quantiles(y, q)
df["scaled_crps"] = df["crps"] / scale
df["covered_80"] = covered(y, df["q0.1"].to_numpy(), df["q0.9"].to_numpy())
```

- A flat history has scale 0; scaled metrics are left undefined there.
- MASE uses the median as the point forecast.
- Scaled CRPS divides by the same seasonal-naive scale, so states with very different demand are comparable.
- 80% coverage: is the actual between q0.1 and q0.9?

```python
if verify and sha256_file(path) != row.sha256:
    raise RuntimeError(f"{row.path} does not match its manifest hash; refusing to score")
```

- In `load_committed`: scoring refuses to run on a file that does not match its hash.

### Likely questions

1. **Why CRPS and not just MAE?** CRPS scores the whole predicted distribution. A model with the right median but intervals that are far too narrow or too wide gets penalised. For a point forecast CRPS reduces to absolute error.
2. **Why scale CRPS?** Raw CRPS is in the series' units (MU, MW, AQI). Dividing by the in-sample seasonal difference makes series comparable and is the same scale as MASE.
3. **Why median for MASE and not mean?** The median minimises absolute error, which is what MASE measures. All models produce a median; not all produce a mean.
4. **Is nine quantiles enough for CRPS?** It is a coarse approximation that ignores the tails beyond 0.1 and 0.9. It is the same approximation GluonTS and fev use, and it is applied identically to every model.
5. **Why rebuild all scores each time instead of incremental scoring?** It is cheap at this size, and rebuilding from committed files means scores can always be reproduced from scratch.

### Weak points and honest responses

- **Tails are ignored.** Extreme AQI events or grid stress days are in the tails. A model with bad tails is not penalised much. Adding 0.01 and 0.99 quantiles would help but changes the contract.
- **Coverage is only for 80%.** The paper plan adds coverage for all four intervals and PIT histograms.
- **Scaled CRPS can blow up for near-flat histories.** The scale is in the denominator. A scale of exactly 0 is excluded; a very small one is not.

---

## 10. Leaderboard aggregation and bootstrap

File: `src/bhavishya/arena/leaderboard.py`.

### What it does and why

Turns per-forecast scores into one skill number per model, with an interval. Skill is the geometric mean over series of the ratio (model mean metric / seasonal naive mean metric), on forecasts both models made. Intervals come from resampling whole run dates. No model is ranked before 28 days live and 10,000 scored forecasts.

### Key code

```python
def paired(scores, model, metric, ref=REFERENCE_MODEL):
    a = scores.loc[scores["model"] == model, [*KEY, metric]].rename(columns={metric: "m"})
    b = scores.loc[scores["model"] == ref, [*KEY, metric]].rename(columns={metric: "r"})
    both = a.merge(b, on=KEY)
    return both[np.isfinite(both["m"]) & np.isfinite(both["r"])]
```

- Keep only (series, run date, horizon) keys where both the model and the reference have a finite score. A model that fails on hard days cannot gain by missing them.

```python
def _geo_ratio(both):
    per_series = both.groupby("series_id")[["m", "r"]].mean()
    per_series = per_series[(per_series["m"] > 0) & (per_series["r"] > 0)]
    return float(np.exp(np.log(per_series["m"] / per_series["r"]).mean())), len(per_series)
```

- Mean metric per series for each model, then the ratio per series, then the geometric mean (exp of mean log). A halving and a doubling cancel out, and one huge series does not dominate.

```python
days = both["run_date"].unique()
by_day = {d: g for d, g in both.groupby("run_date")}
rng = np.random.default_rng(seed)
for _ in range(n_boot):
    sample = rng.choice(days, size=len(days), replace=True)
    draws.append(_geo_ratio(pd.concat([by_day[d] for d in sample], ignore_index=True))[0])
lo, hi = np.nanpercentile(draws, [2.5, 97.5]) if len(days) > 1 else (nan, nan)
```

- Resample run dates with replacement, keeping all forecasts from a sampled day together, and recompute the skill. The 2.5th and 97.5th percentiles give a 95% interval. Fixed seed for reproducibility.

```python
"eligible": n_scored >= MIN_SCORED and days_live >= MIN_DAYS_LIVE,
...
board.loc[eligible, "rank"] = np.arange(1, int(eligible.sum()) + 1)
```

- Only eligible models get a rank. The site says plainly when no model is ranked yet.

### Likely questions

1. **Why geometric mean of ratios and not arithmetic mean of scores?** Arithmetic means of scaled scores are dominated by hard series. Ratios to a reference are scale-free, and the geometric mean treats improvements and degradations symmetrically. fev-bench reports a similar skill score against a baseline.
2. **Why bootstrap over run dates and not individual forecasts?** Forecasts on the same day share weather, holidays and grid events, so they are correlated. Resampling individual rows would give intervals that are far too narrow.
3. **Why 28 days and 10,000 forecasts?** 28 days means at least one full horizon has been scored and a few weekly cycles have passed. 10,000 forecasts keeps intervals from being meaningless. Both were fixed before launch.
4. **What does a skill of 0.9 mean?** On the typical series, the model's scaled CRPS is about 10% lower than seasonal naive's.
5. **How do you compare two non-reference models?** Compare their skill intervals, or compute the ratio of one to the other directly with the same code. The paper plan adds Diebold-Mariano tests and a model confidence set.

### Weak points and honest responses

- **Day-level bootstrap ignores overlap across days.** Forecasts from run dates up to 27 days apart share target dates, so their errors are correlated. A moving-block bootstrap would be better. The paper plan includes it.
- **The ranking sorts by point skill only.** Two models with overlapping intervals get different ranks. The site shows the intervals next to the rank for that reason.
- **Series with zero mean metric are dropped from the geometric mean.** Rare, but it means the number of series behind a skill value can differ by model. `n_series` is returned for that reason.

---

## 11. Health monitoring

File: `src/bhavishya/arena/health.py`.

### What it does and why

Judges each source after the daily fetch as `ok`, `failed` (download or listing error), `contract` (data broke its contract) or `stale` (newest value older than the contract allows). Unhealthy sources are skipped for the day. Every judgement is appended to `health/source_health.csv`, and an issue body is written for CI to open or update a GitHub issue.

### Key code

```python
if result.errors:
    return SourceHealth(source.name, "failed", "; ".join(result.errors)[:1000], newest_s)
if result.contract_errors:
    return SourceHealth(source.name, "contract", "; ".join(result.contract_errors)[:1000], newest_s)
if pd.isna(newest) or (run_date - newest).days > source.contract.max_staleness_days:
    return SourceHealth(source.name, "stale", ..., newest_s)
return SourceHealth(source.name, "ok", f"{result.ok_files} new file(s)", newest_s)
```

- Ordered checks: download errors first, then contract errors, then staleness. The first that applies wins. Details are truncated so issues stay readable.

```python
def issue_title(source: str) -> str:
    # Stable title so CI can find an existing open issue instead of filing duplicates.
    return f"Source health: {source} skipped"
```

- One issue per source. The workflow comments on it if it exists, else creates it.

`build_status` produces the status page: last success per source and model, last state, and gaps in the last 30 runs.

### Likely questions

1. **Why skip a whole source on one bad file?** Any contract error means the source may have changed format. Forecasting from possibly wrong data is worse than a recorded gap.
2. **What is "stale"?** The newest value is more than 3 days older than the run date (the contract's `max_staleness_days`).
3. **Are gaps filled later?** No. A skipped day stays a gap. Forecasts are never backfilled.
4. **How do you avoid issue spam?** A stable title per source; the workflow searches for an open issue with that title and comments instead of opening a new one.
5. **Who fixes a broken parser?** The maintainer, with recorded fixtures for the new layout. The gap is visible on the status page meanwhile.

### Weak points and honest responses

- **Any contract error skips the source**, even if most files were fine. That is strict on purpose but can lose days over one bad historical re-upload in the 10-day window.
- **No alert beyond a GitHub issue.** Fine for a single maintainer who watches issues.

---

## 12. Site

File: `src/bhavishya/arena/site.py` (plus `arena/charts.py`).

### What it does and why

Generates a static site: leaderboard, one page per series with fan charts, methodology, data (sources, attribution, manifest), and status. No external scripts, fonts or trackers. Every chart title states its takeaway, computed from the data.

### Key code

```python
def leaderboard_takeaway(board):
    if board.empty:
        return "No forecasts have been scored yet"
    ranked = board[board["eligible"]]
    if ranked.empty:
        return (f"No model is ranked yet: ranking needs {lb.MIN_DAYS_LIVE} days live and "
                f"{lb.MIN_SCORED:,} scored forecasts")
```

- The headline is computed. Before thresholds are met, the site says so instead of showing a winner.

```python
def _env() -> Environment:
    return Environment(autoescape=select_autoescape(default=True))
```

- Jinja autoescaping on by default. Series names, model names and submission metadata are escaped, and tables use `html.escape` on every cell.

```python
'<p class="note">Limitations: young benchmark, few series, two sources. Rankings are provisional until '
```

- The limitations note is on the front page, not hidden in docs.

### Likely questions

1. **Why a static site?** No server to run or secure, hosts free on GitHub Pages, and it can be rebuilt from the data branch by anyone.
2. **Why compute chart titles?** A title like "No model is ranked yet" or "X leads, 12% better than seasonal naive (interval ...)" tells the reader the point and cannot drift out of sync with the data.
3. **How do you prevent XSS from submission names?** Autoescape plus `html.escape` on table cells. Submission names are also restricted by a regex to lower-case letters, digits and underscores.
4. **Where does a reader verify a forecast?** The data page lists manifest hashes and links to the data branch.
5. **How does the filter work without a framework?** All tables are rendered server-side; a few lines of inline script show one at a time.

### Weak points and honest responses

- **The whole site rebuilds every day.** Fine at this size.
- **Docs and CLI names.** The data page once said `bhavishya arena verify`; the command is `bhavishya verify`. Fixed.

---

## 13. Submissions sandbox

Files: `src/bhavishya/arena/submissions.py`, `models/container.py`, `.github/workflows/submission.yml`, SECURITY.md.

### What it does and why

Outside teams submit a folder with `model.yaml`, `forecast.py` (a `Forecaster` subclass), `requirements.txt` and a `Dockerfile`. The arena validates metadata, builds the image (network allowed at build time to download weights), runs it with no network and strict limits, and re-validates the output on the host with trusted code.

### Key code

```python
cmd = [
    "docker", "run", "--rm",
    "--network", "none",
    "--memory", LIMITS["memory"], "--memory-swap", LIMITS["memory"],
    "--cpus", LIMITS["cpus"], "--pids-limit", LIMITS["pids"],
    "--read-only", "--tmpfs", "/tmp:rw,size=512m",
    "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
    "-v", f"{history.resolve()}:/input/history.parquet:ro",
    "-v", f"{work.resolve()}:/output:rw",
    ...
]
```

- `--network none`: no way to fetch outcomes or exfiltrate.
- `--memory 6g` with equal `--memory-swap`: hard memory cap, no swap.
- `--cpus 2`, `--pids-limit 256`: CPU cap and no fork bombs.
- `--read-only` with a 512 MB `/tmp`: the container cannot modify its own filesystem.
- `--cap-drop ALL`, `no-new-privileges`: no Linux capabilities, no privilege escalation.
- Only the history file is mounted, read-only. Output goes to one empty folder.

```python
raw = pd.read_parquet(work / "forecasts.parquet")
expected = sorted(pd.read_parquet(history)["series_id"].unique())
# Re-validate on the host: never trust the container's own checks.
return finalize_forecast(
    raw.drop(columns=["cutoff", "target_date"], errors="ignore"), cutoff, HORIZON, expected
)
```

- Drop any cutoff or target dates the container wrote, and run the same `finalize_forecast` checks as built-in models, using the series list from the trusted input file.

```python
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
```

- Names are safe for file paths, Docker tags and HTML.

Workflow security (submission.yml): trigger is `pull_request` with `types: [labeled]`, never `pull_request_target`, so fork PRs get a read-only token and no secrets. It runs only when a maintainer applies `run-submission`, and checks out the exact head commit at label time with `persist-credentials: false`.

### Likely questions

1. **Why `pull_request` and not `pull_request_target`?** `pull_request_target` runs with the base repo's write token and secrets, which is a known path to repo takeover when it checks out PR code. `pull_request` from a fork gets a read-only token.
2. **What stops a submitter pushing malicious code after approval?** The workflow runs only on the `labeled` event at the labelled commit. New pushes do not run until a maintainer labels again.
3. **Can a submission read future data?** It has no network and only a history file already truncated at the cutoff.
4. **Why allow network at build time?** To install packages and download weights. The build output is a static image; the forecast step has no network.
5. **Why re-validate on the host?** The container is untrusted. Its own checks could be removed or faked.

### Weak points and honest responses

- **Docker is not a perfect sandbox.** Container escapes exist. The runner is an ephemeral GitHub-hosted VM with no secrets, which limits the damage.
- **Build-time network means a submission could fetch anything during build.** At build time there is no future data to fetch beyond what is public, but a submission could bake in data published after its training cut. The rule that models declare their training data, and the fact that forecasts are only scored from the day they start, limit the effect.
- **Maintainer review is the real gate.** A careless approval is a risk. CODEOWNERS on `.github/` is recommended.

---

## 14. CI workflows

Files: `.github/workflows/ci.yml`, `daily.yml`, `score-and-site.yml`, `submission.yml`, `release.yml`.

### What it does and why

- `ci.yml`: lint (ruff), format check, type check (mypy) and tests on Python 3.10 and 3.12, read-only permissions.
- `daily.yml`: at 05:45 UTC (11:15 IST). Job 1 fetches, records health, opens issues, prepares inputs and pushes them. Job 2 is a matrix with one job per model, read-only. Job 3 runs merged submissions in Docker. Job 4 downloads all staged outputs, commits, hashes, timestamps and pushes.
- `score-and-site.yml`: after each daily run and weekly. Verifies all hashes, scores, commits scores, builds the site and deploys to Pages.
- `submission.yml`: label-gated sandboxed run for PRs.
- `release.yml`: on a version tag, builds and publishes to PyPI with OIDC trusted publishing (no stored token).

### Key code

```yaml
concurrency:
  group: arena-data  # only one job may write to the data branch at a time
  cancel-in-progress: false
```

- The daily and scoring workflows share a concurrency group, so they never push to `data` at the same time, and a queued run is not cancelled.

```yaml
if: ${{ vars.ARENA_ENABLED == 'true' || github.event_name == 'workflow_dispatch' }}
```

- Scheduled runs only start after the maintainer flips a repository variable. Manual runs always work.

```yaml
  model:
    permissions:
      contents: read  # models never get write access or secrets
    strategy:
      fail-fast: false  # one failing model must not cancel the others
```

- Model jobs cannot write to the repo. One model failing does not cancel the rest.

```yaml
  commit:
    needs: [fetch-prepare, model, submissions]
    if: ${{ always() && needs.fetch-prepare.result == 'success' }}
```

- Commit runs even if some models failed, as long as inputs were prepared. Failures are recorded in `run.json`.

```yaml
      - name: Verify every forecast file against the manifest
        run: bhavishya verify
```

- Scoring never starts without a full hash check.

### Likely questions

1. **Why split the daily run into jobs?** Different Python environments per model, least privilege (only fetch and commit jobs can write), and parallelism.
2. **Why 11:15 IST?** After Grid-India's morning report for the previous day, and after CPCB's previous-evening bulletin.
3. **How do staged outputs get to the commit job?** As workflow artifacts, merged in the commit job.
4. **Why OIDC for PyPI?** No long-lived token to leak.
5. **What if GitHub Actions is down for a day?** That run date is a gap. Forecasts are never made late for a past date, because that would not be prospective.

### Weak points and honest responses

- **GitHub Actions timing is not guaranteed.** Scheduled jobs can start late under load. That matters for CPCB horizon 1 (see section 7).
- **Raw files are kept as 90-day artifacts only.** The long-term raw archive is the maintainer's local store, so outside verification of raw hashes depends on re-downloading from the source.
- **Single maintainer, single CI provider.** A mirror on another platform would add resilience.

---

## Cross-cutting questions

1. **What is the main contribution, honestly?** An open, prospective, hash-committed benchmark on Indian public series, plus loaders with vintage snapshots. Not the idea of a live benchmark.
2. **How is this different from TS-Arena?** TS-Arena is the closest prior art: pre-registered live forecasts on energy data, with server-side windows. Bhavishya uses Indian series, publishes hashes in git with OpenTimestamps so timing is verifiable without trusting a server, and scores quantile forecasts with CRPS and coverage. TS-Arena's paper reports point-forecast scoring.
3. **What would you do with more time?** Moving-block bootstrap, coverage at all levels, Agmarknet, covariates, a longer window, and a check of commit time against publication time for every horizon-1 target.
4. **What results do you have?** None yet. It launched on 2026-10-27. Rankings need 28 days live and 10,000 scored forecasts.
5. **What was the hardest bug class?** Off-by-one-day issues between IST and UTC and between observation date, publication date and fetch date. The contract's midnight check and IST dates everywhere came from that.

---

## Glossary

**Prospective evaluation.** Scoring forecasts that were made and recorded before the target value existed. The opposite is retrospective (backtest) evaluation on data that already existed.

**Static benchmark.** A fixed dataset split into training and test periods, scored after the fact. Easy to reproduce, but the test data may have been seen by models trained later.

**Data leakage.** Any path by which information from after the forecast cutoff reaches the model or the scoring choices. Examples: using revised values that were not known at the time, interpolating gaps with future values, tuning on the test period, or a foundation model having the test data in its pretraining corpus.

**Contamination.** Leakage through pretraining data: the evaluation series (or highly correlated ones) were in the model's training data.

**Cutoff.** The last date of history given to a model. In Bhavishya, one cutoff per source per run date.

**Run date.** The IST date on which a forecast is made and committed.

**Horizon.** Days between the cutoff and the target date (1 to 28).

**Vintage.** The date on which a version of a value was known. The same observation can have several vintages if the source revises it.

**First release.** The earliest vintage of a value. Bhavishya scores against it.

**As-of view.** The data as it was known on a given date: for each observation, the latest vintage on or before that date.

**Revision.** A change to a previously published value.

**Data contract.** A written set of rules (schema, units, ranges, frequency, minimum rows, staleness) that a source's data must pass before use.

**Quantile.** The value below which a given share of the distribution falls. q0.1 is the 10% quantile.

**Quantile crossing.** When a model's predicted q0.2 is below its q0.1, for example. Bhavishya sorts quantiles to remove it.

**Quantile loss (pinball loss).** For level tau and quantile forecast q: tau times (y minus q) if y is above q, else (1 minus tau) times (q minus y). Minimised in expectation by the true tau-quantile.

**CRPS (continuous ranked probability score).** A proper scoring rule for a whole predictive distribution: the integral of squared difference between the predicted CDF and the step function at the actual. It equals twice the integral of the pinball loss over all levels. Bhavishya approximates it as twice the mean pinball loss over nine levels. Lower is better. For a point forecast it equals absolute error.

**Proper scoring rule.** A score that is optimised in expectation by reporting your true belief. CRPS and pinball loss are proper; coverage alone is not.

**MASE (mean absolute scaled error).** Absolute error divided by the in-sample mean absolute seasonal difference (here, 7-day difference). Below 1 means smaller errors than a seasonal naive forecast had in sample.

**Scaled CRPS.** CRPS divided by the same MASE scale, so series in different units are comparable.

**Seasonal naive.** Forecast equals the value one season ago (here, 7 days ago). The reference model.

**Skill (relative skill).** Ratio of a model's score to the reference's score. Bhavishya uses the geometric mean over series of per-series ratios. Below 1 is better than seasonal naive.

**Geometric mean.** The exponential of the mean of logs. For ratios, it treats 0.5 and 2 as equal and opposite.

**Coverage.** The share of actuals that fall inside a prediction interval. An 80% interval should cover about 80%. Too high means intervals are too wide; too low means too narrow.

**Calibration.** Agreement between predicted probabilities and observed frequencies. Checked with coverage and PIT histograms.

**PIT (probability integral transform).** The predictive CDF evaluated at the actual. For a calibrated forecast, PIT values are uniform. With quantile forecasts, you count which of the 10 bins between quantiles each actual falls into.

**Bootstrap.** Estimating uncertainty by resampling the data with replacement and recomputing the statistic.

**Block bootstrap.** Resampling blocks (here, whole run dates) instead of single rows, to keep correlated observations together.

**Moving-block bootstrap.** Resampling runs of consecutive blocks (for example 7 consecutive run dates) to keep serial correlation too.

**Diebold-Mariano test.** A test of whether two forecasters have equal expected loss, based on the mean of the loss difference and a variance that accounts for autocorrelation.

**Model confidence set (MCS).** A set of models that contains the best model with a given confidence, built by eliminating models that are significantly worse.

**Conformal prediction.** A method that builds prediction intervals from past out-of-sample errors (calibration residuals), with a coverage guarantee if the errors are exchangeable. mlforecast does this with a few rolling windows.

**Exchangeability.** The assumption that the order of observations does not change their joint distribution. Time series usually violate it, so conformal guarantees are approximate.

**ETS.** Exponential smoothing with error, trend and seasonal components. AutoETS picks the form by information criterion.

**ARIMA.** Autoregressive integrated moving average. AutoARIMA picks orders automatically.

**Global model.** One model trained across many series (LightGBM here), as opposed to one model per series (ETS, ARIMA).

**Foundation model (time series).** A large model pretrained on many time series, used on new series without training. Chronos-2, TimesFM 2.5 and Moirai 2.0 are examples.

**Zero-shot.** Using a pretrained model on a new series with no training or fine-tuning on that series.

**Fine-tuning.** Further training of a pretrained model on target-domain data. Not done in Bhavishya's built-in models.

**Context length.** How much history a foundation model reads. Capped at 1,024 days here.

**Covariate.** An extra input series (for example temperature) that may help forecast the target. Not used by built-in models at launch.

**Panel.** The fixed list of target series, chosen by written rules before launch.

**SHA-256.** A cryptographic hash function. Any change to a file changes its hash.

**Manifest.** An append-only CSV listing each forecast file and its SHA-256.

**OpenTimestamps.** An open protocol that aggregates hashes from many users via public calendar servers and anchors them in Bitcoin transactions, proving a hash existed by a certain time.

**Commit-reveal.** Publishing a hash of a prediction first and the prediction later. Bhavishya publishes both at once; the hash and timestamp prove the file did not change.

**Tamper evidence.** Changes are detectable, not impossible.

**Vintage store.** Bhavishya's storage of every version of every value, keyed by vintage.

**Forward fill.** Filling a missing value with the last known value. Uses no future data.

**OIDC trusted publishing.** Publishing to PyPI with a short-lived token issued to a specific GitHub workflow, so no API token is stored.

**`pull_request_target`.** A GitHub Actions trigger that runs with the base repository's permissions and secrets. Dangerous with untrusted PR code. Bhavishya does not use it.

**MU (million units).** One million kWh, equal to one GWh. The unit of Grid-India energy met.

**National AQI.** India's Air Quality Index, 0 to 500, computed by CPCB from several pollutants. The bulletin reports a 24-hour value to 16:00 IST.

**PSP report.** Grid-India's daily Power Supply Position report.
