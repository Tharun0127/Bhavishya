# Data sources

Status as verified from a residential Indian connection on 2026-10-27.

## Shipped

### Grid-India daily Power Supply Position report (`grid_india`)

- Publisher: Grid Controller of India Ltd (Grid-India), National Load Despatch Centre. A Government of India enterprise.
- Page: https://grid-india.in/en/reports/daily-psp-report
- Access: keyless. File list from `POST https://webapi.grid-india.in/api/v1/file`, files from `https://webcdn.grid-india.in/`. We read the XLS version.
- Release: the report for day D is published on day D+1, usually before 10:00 IST.
- History: monthly listings go back several years. The arena backfills from 2025-04-01.
- Series: `grid_india/energy_met/<state>` (MU, million units = GWh), `grid_india/max_demand/<state>` (MW), and `.../all_india` for both.
- Contract: daily, MU in [0, 10000], MW in [0, 400000], at least 20 rows per file, stale after 3 days.
- Licence: the site's copyright page could not be loaded on 2026-10-27, so the terms are unverified. We treat the report as a public government record. We do not redistribute the files. We publish derived daily values with attribution and the SHA-256 of each file. Permission to republish is a launch checklist item (docs/LAUNCH_CHECKLIST.md).
- Attribution: "Source: Grid Controller of India Ltd (Grid-India), Daily PSP Report."
- Known issues: state names change occasionally (for example "J&K(UT) & Ladakh"). New names become new series ids. Rows for bulk consumers and railways are skipped.

### CPCB daily AQI bulletin (`cpcb_aqi`)

- Publisher: Central Pollution Control Board, Ministry of Environment, Forest and Climate Change.
- Page: https://cpcb.nic.in/AQI_Bulletin.php
- Access: keyless. `https://cpcb.gov.in/upload/Downloads/AQI_Bulletin_YYYYMMDD.pdf`. The `cpcb.nic.in` https host did not answer from our network; its http URL redirects to `cpcb.gov.in`.
- Release: the bulletin for day D is published on the evening of day D. Each value is a 24-hour average ending 16:00 IST.
- History: reachable back to at least 2023. Some days return 404 (for example 2025-01-01 and 2026-10-24 and 2026-10-25). Missing days are recorded as gaps, never filled.
- Series: `cpcb_aqi/aqi/<city>`, the National AQI (unitless, 0 to 500).
- Contract: daily, AQI in [0, 500], at least 50 cities per file, stale after 3 days.
- Licence: CPCB's copyright policy (updated 2019-09-01) allows material to be downloaded without prior permission. "Any other proposed use of the material is subject to the approval of competent authority of CPCB" (ccb.cpcb@nic.in). The pip package only downloads to the user's machine. The arena publishes derived values with attribution and file hashes, not the PDFs. Permission to republish is a launch checklist item. Fallback: the same CPCB data is on data.gov.in under the Government Open Data License - India.
- Attribution: "Source: Central Pollution Control Board (CPCB), Daily AQI Bulletin."

### Open-Meteo (`open_meteo`), covariates only

- Publisher: Open-Meteo.com. Values are model output (reanalysis and forecast blends), not observations.
- Access: keyless. Archive API for older days, forecast API with past days for the last 6 days.
- Series: `open_meteo/<variable>/<city>` for daily max and mean 2 m temperature (degC) and precipitation (mm) in 12 cities.
- Licence: data under CC BY 4.0. The free API is for non-commercial use (https://open-meteo.com/en/terms). Heavy or commercial use needs a paid plan.
- Attribution: "Weather data by Open-Meteo.com (CC BY 4.0)."
- Not an arena target: values are revised freely and are not an Indian public record. See docs/DECISIONS.md D3.

## Planned, with the reason they were deferred

| Source | Why deferred | What unblocks it |
|---|---|---|
| Agmarknet mandi prices via data.gov.in (resource `9ef84268-d588-465a-a308-a864a43d0070`) | Needs a data.gov.in API key. None was available at build time. The resource returns current prices only, so history must be built from daily snapshots. | Add `DATA_GOV_IN_API_KEY` to `.env` and GitHub secrets. Data is under the Government Open Data License - India. |
| Agmarknet 2.0 portal API (`api.agmarknet.gov.in`) | Report endpoints return `TOKEN_OR_CAPTCHA_REQUIRED`. We do not bypass CAPTCHAs. | None. Use data.gov.in instead. |
| CPCB real-time AQI via data.gov.in | Needs the same key. Real-time station values only, no history. | Key. Useful as a GODL-licensed fallback for the AQI track. |
| IMD rainfall and city weather APIs | Endpoints reply "IP needs to be whitelisted". | IMD whitelisting, or the `imdlib` gridded data (lagged, not daily-live). |
| Retail fuel prices (IOCL, PPAC) | Metro prices stay flat for months. A target with no variation cannot separate models. | Revisit if prices move daily again. |
