# Decisions

Each entry records a choice made during the build, the reason, and what would change it. Newest entries go at the bottom.

## D1. Project and package name

- Project: Bhavishya (IndiaCast Arena). The repository owner renamed the repository to `Bhavishya`.
- Python package and import name: `bhavishya`. It was free on PyPI on 2026-10-27 (see docs/PRIOR_ART.md).
- Reason: one name for repo, package and site avoids confusion.

## D2. Novelty framing

- The README does not claim to be the first live forecasting benchmark. TS-Arena, Impermanent and LiveHouse-TS already run live TSFM evaluation.
- The claim is limited to: prospective, hash-committed evaluation on Indian public series, plus vintage-aware loaders. See docs/PRIOR_ART.md section 6.

## D3. Launch sources

Verified on 2026-10-27 from this machine:

| Source | Result | Decision |
|---|---|---|
| Grid-India daily PSP report | Keyless JSON listing API plus XLS and PDF files. History available by month. | Ship. |
| CPCB daily AQI bulletin (PDF) | Keyless. Archive reachable back to at least 2023, with some missing days. | Ship. |
| Open-Meteo | Keyless JSON API. | Ship as a covariate loader, not as a forecast target. |
| Agmarknet via data.gov.in | Needs a data.gov.in API key. No key was available. | Defer until a key is added. |
| Agmarknet 2.0 portal API | Report endpoints return `TOKEN_OR_CAPTCHA_REQUIRED`. | Do not use. We do not bypass CAPTCHAs. |
| CPCB via data.gov.in | Needs the same key. Real-time only, no history. | Defer. The bulletin covers the same cities with history. |
| IMD APIs | Return "IP needs to be whitelisted". | Defer. |
| Retail fuel prices | Prices in metros change rarely (long flat periods). A forecasting target with no variation does not separate models. | Defer. |

- The brief asked to stop if a required key was missing. The key is only required for Agmarknet. Three sources work without it, so the build continued and Agmarknet is listed as planned. The launch checklist explains how to get the key.
- Open-Meteo counts as the third shipped source, but it is not an arena target. Its data is model output (forecast and reanalysis blends), not an Indian public record, and it revises freely. It is used for covariates and future work only.

## D4. Model environments are isolated

- `uni2ts` (Moirai) pins `torch<2.5`, `numpy~=1.26` and `scipy~=1.11`. These conflict with current `statsforecast`, `chronos-forecasting` and `timesfm`.
- Every model therefore runs in its own process, and Moirai runs in its own virtual environment. In GitHub Actions each model is a separate matrix job.
- Side benefit: one model crashing or timing out cannot stop the others. The process boundary is also the main leakage guard (see D7).

## D5. Licences: raw files are not redistributed; hashes are

- CPCB's copyright policy (cpcb.gov.in/copyright-policy, updated 2019-09-01) allows material to be "downloaded to file or printer without requiring specific prior permission". Any other use needs approval from CPCB (ccb.cpcb@nic.in).
- Grid-India's copyright and website policy pages did not load outside the site's own navigation on 2026-10-27, so their terms are unverified.
- Open-Meteo data is CC BY 4.0.
- Decision:
  - The pip package downloads files to the user's own machine, which the CPCB policy allows.
  - The arena publishes derived numbers (daily values), forecasts and scores with attribution. It publishes the SHA-256 of every raw file it used, but not the raw Grid-India or CPCB files. Anyone can re-download a file from the source and check the hash. Raw files are kept as 90-day workflow artifacts and in the maintainer's local store.
  - Before the site goes public, the maintainer should ask CPCB and Grid-India for permission to republish derived daily values. Draft emails are in docs/launch/. This is on the launch checklist.
  - If CPCB refuses, switch the AQI track to CPCB data on data.gov.in, which is released under the Government Open Data License - India (needs the API key).
- Why not wait: the loaders and the pipeline are useful and testable now. Publication is a separate, manual step that the maintainer controls.

## D6. Foundation model versions

Checked on Hugging Face on 2026-10-27:

| Family | Latest found | Used | Why |
|---|---|---|---|
| Chronos | `amazon/chronos-2` (rev `29ec376`) | same | Latest; about 120M parameters; runs on CPU. |
| TimesFM | `google/timesfm-3.0-pytorch` (rev `43046b8`, 1.3 GB) | `google/timesfm-2.5-200m-pytorch` (rev `1d95242`) | TimesFM 3.0 is under the "TimesFM Non-Commercial License v1.0", and its code (`timesfm3`) is not on PyPI (`timesfm` 3.0.2 only imports it if present). 2.5 is Apache-2.0 and supported by the released package. Revisit when `timesfm3` is released. |
| Moirai | `Salesforce/moirai-2.0-R-small` (rev `30f43ff`) | same | Latest Moirai on the Hub; 11M parameters. |

Revisions are pinned in `src/bhavishya/models/foundation.py`. The SHA-256 of each weights file is recorded with every forecast.

## D7. Leakage guard

- The arena writes each model's input file from `store.as_of(run_date)`, truncated at the cutoff. The model process gets only that file.
- `Forecaster.forecast` raises `LeakageError` if history goes past the cutoff. Tests cover both.
- In CI, model jobs have read-only permissions. Submissions also run with `--network none`.

## D8. Where arena data lives: a `data` branch in the same repository

- Options: a separate branch, a separate repository, or a Hugging Face dataset.
- Chosen: an orphan `data` branch. It needs no extra token or account, its history is the tamper-evidence record, and `main` stays small. Raw source files are not committed there (D5).
- Expected growth: about 40 KB per day of parquet (forecasts, inputs, observations). Under 20 MB a year.
- Revisit if the data branch passes 1 GB: move to a Hugging Face dataset and keep only the manifest on GitHub.

## D9. OpenTimestamps

- Done with the `opentimestamps` Python library against two public calendars. The `ots` command needs OpenSSL through ctypes and fails on Windows, so the library is used directly.
- A failed stamp never blocks a commit. The git push is the primary record.
- Proofs are upgraded (Bitcoin attestation added) by the scoring job on later days.

## D10. Scoring against the first release

- Chosen because it is the value that existed when the outcome first became public, and it fixes scores once. See docs/METHODOLOGY.md section 5.

## D11. Ranking thresholds

- 28 days live and 10,000 scored forecasts. With about 37 series and 28 horizons, a model reaches 10,000 scored forecasts in roughly three to four weeks of daily runs. So both conditions bind at about the same time.
- These are judgement calls. They are written down now so they cannot be tuned after seeing results.

## D12. Missing days

- Missing source days are never invented in the store.
- Model inputs forward-fill gaps so every model gets a regular daily series. The count of filled values is recorded per run.
- Days with no published actual are not scored.
