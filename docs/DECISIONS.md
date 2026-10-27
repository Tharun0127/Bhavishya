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
