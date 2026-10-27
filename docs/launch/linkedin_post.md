# DRAFT: LinkedIn launch post (not posted)

---

I have launched Bhavishya (IndiaCast Arena), a live forecasting arena for Indian public data.

What it does:

Every day, seven time series models forecast two Indian public datasets 1 to 28 days ahead, before the numbers are published:

- Grid-India daily energy met (national and 15 states)
- CPCB daily city AQI (up to 20 cities)

The models are seasonal naive, AutoETS, AutoARIMA, LightGBM, and three zero-shot foundation models: Chronos-2, TimesFM 2.5 and Moirai 2.0 small.

Each day's forecasts go into one file. The file is SHA-256 hashed, the hash is added to an append-only manifest, and both are committed to a public git branch with an OpenTimestamps proof, before any outcome exists. When the real values come out, the forecasts are scored against the first published value: MASE, quantile CRPS, 80% interval coverage, and skill relative to seasonal naive with bootstrap intervals.

Why: static benchmarks reuse public data that newer models may have seen in training. A forecast made before the data exists cannot have that problem.

The honest limitations:

- There are no results yet. It started on 27 October 2026. No model is ranked until it has 28 days live and 10,000 scored forecasts.
- Two sources, a few dozen series, one season so far.
- Live forecasting benchmarks are not new. TS-Arena, Impermanent and LiveHouse-TS already do this for foundation models. What is new here is narrower: Indian public series, hash-committed forecasts, and loaders that keep every version of the data.
- Each model runs one fixed configuration on CPU. The model teams could probably do better, and they are welcome to submit.
- Mandi prices (Agmarknet) are planned but need a data.gov.in key.

You can:

- Watch the leaderboard: <LEADERBOARD_URL>
- Read the code and the data branch: https://github.com/Tharun0127/Bhavishya
- Submit a model through a pull request (it runs in a sandbox with no network)
- Tell me where the method is wrong. Issues are open.

Data: Grid-India daily PSP reports and CPCB daily AQI bulletins, republished as derived daily values with attribution.

#forecasting #timeseries #opendata #India
