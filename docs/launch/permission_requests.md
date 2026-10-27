# DRAFT, NOT SENT: permission requests to republish derived values

Two draft emails. Neither has been sent. The maintainer sends them personally, from his own address, before the public site is promoted. Fill in the placeholders in angle brackets. Keep a copy of any reply in a private folder and record the outcome (date, decision, conditions) in docs/DECISIONS.md D5.

Background: docs/DECISIONS.md D5 and DATA_SOURCES.md. CPCB's copyright policy (cpcb.gov.in/copyright-policy, updated 2019-09-01) allows material to be downloaded without prior permission and says any other use needs approval from CPCB at ccb.cpcb@nic.in. Grid-India's copyright page could not be loaded on 2026-10-27, so its terms are unverified.

---

## 1. Email to CPCB (DRAFT, NOT SENT)

**To:** ccb.cpcb@nic.in
**Subject:** Request for permission to republish derived daily AQI values with attribution (non-commercial open benchmark)

Dear Sir or Madam,

I am writing to request permission, under CPCB's copyright policy, to republish values derived from the CPCB Daily AQI Bulletin for a non-commercial, open research benchmark.

**About the project.** Bhavishya (IndiaCast Arena) is an open-source project that tests forecasting methods on Indian public data. Each day, computer models forecast the next 1 to 28 days of the National AQI for up to 20 large cities. The forecasts are recorded before the bulletin is published and compared with the published values afterwards. The aim is to learn which methods forecast Indian air quality well. The project earns no money and carries no advertising. The code is public at https://github.com/Tharun0127/Bhavishya.

**What we would publish.**

1. The daily AQI value for each selected city and date, as read from the bulletin.
2. Forecasts of these values made by the models.
3. Scores comparing forecasts with the published values.
4. The SHA-256 checksum of each bulletin file we used, so anyone can check that a value came from a specific CPCB file.

**What we would not publish.** We would not republish or host the original PDF bulletins. Anyone who wants a bulletin is directed to the CPCB website.

**Attribution.** Every page and data file that shows these values would carry: "Source: Central Pollution Control Board (CPCB), Daily AQI Bulletin," with a link to https://cpcb.nic.in/AQI_Bulletin.php. We would state clearly that the forecasts are ours, not CPCB's, and that CPCB does not endorse the project.

**Access.** We download one bulletin per day, at most one request per second, with a User-Agent that names the project.

We would be grateful to know whether this use is acceptable, and whether CPCB would like any change to the attribution wording or to what is published. If CPCB prefers, we can instead use the CPCB data published on data.gov.in under the Government Open Data License - India.

Thank you for your time.

Yours faithfully,
<Full name> (GitHub: Tharun0127)
<Email address>
<City, India>

---

## 2. Email to Grid-India (DRAFT, NOT SENT)

**To:** <public contact address listed on grid-india.in for website or data queries; confirm before sending>
**Subject:** Request for permission to republish derived daily values from the Daily PSP Report (non-commercial open benchmark)

Dear Sir or Madam,

I am writing to ask for permission to republish values derived from Grid-India's Daily Power Supply Position (PSP) Report for a non-commercial, open research benchmark. I could not find the website's copyright terms (the page did not load for me on 27 October 2026), so I would rather ask directly.

**About the project.** Bhavishya (IndiaCast Arena) is an open-source project that tests forecasting methods on Indian public data. Each day, computer models forecast the next 1 to 28 days of energy met for India and for 15 states, and all-India maximum demand met. The forecasts are recorded before the report is published and compared with the published values afterwards. The project earns no money and carries no advertising. The code is public at https://github.com/Tharun0127/Bhavishya.

**What we would publish.**

1. Daily values read from the PSP report: energy met (MU) for India and for the selected states, and all-India maximum demand met (MW).
2. Forecasts of these values made by the models.
3. Scores comparing forecasts with the published values.
4. The SHA-256 checksum of each report file we used, so anyone can check that a value came from a specific Grid-India file.

**What we would not publish.** We would not republish or host the original XLS or PDF report files. Anyone who wants a report is directed to https://grid-india.in/en/reports/daily-psp-report.

**Attribution.** Every page and data file that shows these values would carry: "Source: Grid Controller of India Ltd (Grid-India), Daily PSP Report," with a link to the report page. We would state clearly that the forecasts are ours, not Grid-India's, and that Grid-India does not endorse the project.

**Access.** We read the public file listing and download the day's report once a day, at most one request per second, with a User-Agent that names the project.

We would be grateful to know whether this use is acceptable, and whether Grid-India would like any change to the attribution wording, to what is published, or to how often we access the site.

Thank you for your time.

Yours faithfully,
<Full name> (GitHub: Tharun0127)
<Email address>
<City, India>
