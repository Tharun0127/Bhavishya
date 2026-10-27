# Bhavishya (IndiaCast Arena)

The live forecasting arena for India.

Time series models forecast Indian public data before it exists. Each day's forecasts are hashed and committed to git before the outcomes are published, then scored automatically as the real numbers arrive.

**Live leaderboard:** `<LEADERBOARD_URL>` (not yet published; see [docs/LAUNCH_CHECKLIST.md](docs/LAUNCH_CHECKLIST.md))

## Limitations (read first)

- **No results yet.** The arena started on 2026-10-27. Rankings need at least 28 days live and 10,000 scored forecasts per model. Expect noisy results for months.
- **Small scope.** Two sources (Grid-India state power demand, CPCB city air quality), about 37 series, daily frequency, one country.
- **Not the first live benchmark.** TS-Arena, Impermanent and LiveHouse-TS already evaluate time series foundation models prospectively. What is specific here is Indian public data, hash-committed forecasts, and vintage-aware loaders. See [docs/PRIOR_ART.md](docs/PRIOR_ART.md).
- **Licences.** CPCB's website terms require permission for reuse beyond downloading. We publish derived daily values with attribution and file hashes, not the original files, and have drafted permission requests. See [DATA_SOURCES.md](DATA_SOURCES.md).
- **Mandi prices are not in yet.** Agmarknet needs a data.gov.in API key.

## Why this exists

Static benchmarks have a contamination problem. A foundation model trained after a dataset was published may have seen the test period. A prospective benchmark cannot leak the future, because the future does not exist yet when the forecast is made.

Indian public data is also hard to use. Formats are PDFs and spreadsheets, histories get revised, and there are few clean loaders. Part one of this project fixes that, independent of the arena.

## Part 1: the data package

```bash
pip install "git+https://github.com/Tharun0127/Bhavishya"   # PyPI release pending: pip install bhavishya
```

```python
import bhavishya

# State-wise daily energy met, from Grid-India's daily reports
power = bhavishya.load("grid_india", "2026-09-01", "2026-10-26")

# City AQI from CPCB's daily bulletin, as it was known on 15 October
aqi = bhavishya.load("cpcb_aqi", "2026-09-01", series=["cpcb_aqi/aqi/delhi"], as_of="2026-10-15")
```

Every loader returns the same columns: `series_id, timestamp, value, unit, source, vintage_date`. Every file is checked against a data contract (schema, units, valid ranges, row counts). Raw files are cached and hashed. See [docs/usage.md](docs/usage.md).

| Source | Series | Key needed | Status |
|---|---|---|---|
| Grid-India daily PSP report | energy met (MU) and peak demand (MW), per state and all-India | no | shipped |
| CPCB daily AQI bulletin | National AQI per city | no | shipped |
| Open-Meteo | daily temperature and rain for 12 cities (covariates) | no | shipped |
| Agmarknet via data.gov.in | mandi prices | yes | planned |

## Part 2: the arena

Every day at 11:15 IST, GitHub Actions:

1. Fetches new source files, checks their contracts, and records what was known that day (the vintage).
2. Builds each model's input from data known that day only, truncated at the latest observation.
3. Runs each model in its own job, with no write access: seasonal naive, AutoETS, AutoARIMA, LightGBM, Chronos-2, TimesFM 2.5 and Moirai 2.0. Each returns 9 quantiles for the next 28 days.
4. Merges the outputs into one file, records its SHA-256 in an append-only manifest, requests an OpenTimestamps proof, and pushes to the `data` branch. All of this happens before any target value is published.

A second job scores forecasts against the first published value of each target: MASE, quantile CRPS and 80% interval coverage. It reports skill relative to seasonal naive, with bootstrap intervals. The full protocol is in [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

Anyone can check the record:

```bash
git clone -b data https://github.com/Tharun0127/Bhavishya arena-data
pip install "git+https://github.com/Tharun0127/Bhavishya#egg=bhavishya[arena]"
bhavishya verify --data-dir arena-data
```

## Submit a model

Copy [`submissions/_template`](submissions/_template), implement one method, and open a pull request. A maintainer reviews the code and applies a label. CI then runs it in a container with no network and no secrets. Details: [CONTRIBUTING.md](CONTRIBUTING.md). Threat model: [SECURITY.md](SECURITY.md).

## Repository layout

```
src/bhavishya/sources/   loaders (one file per source)
src/bhavishya/store.py   vintage store
src/bhavishya/models/    model interface, baselines, foundation models
src/bhavishya/arena/     daily cycle, hashing, scoring, leaderboard, site, submissions
config/                  panel rules and the frozen panel
docs/                    methodology, decisions, prior art, launch kit
data branch              observations, inputs, forecasts, manifest, proofs, scores
```

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[baselines,arena,dev]"
pytest            # fast tests on recorded fixtures
pytest -m slow    # also runs the foundation models (downloads weights)
ruff check src tests && mypy
```

## Licence and citation

Code: Apache-2.0. Data remains under its publishers' terms (see [DATA_SOURCES.md](DATA_SOURCES.md)). Model weights remain under their own licences.

If you use the loaders or the arena, please cite the repository: Tharun0127, *Bhavishya: the live forecasting arena for India*, 2026, https://github.com/Tharun0127/Bhavishya.
