# DRAFT: X thread (not posted)

Each numbered item is one post. Keep each under 280 characters.

---

**1/**
I launched Bhavishya (IndiaCast Arena): a live forecasting arena for Indian public data.

Models forecast Grid-India power demand and CPCB city AQI before the numbers are published. No results yet: it started 27 Oct 2026.

<LEADERBOARD_URL>

**2/**
7 models run every day, 1 to 28 days ahead:
seasonal naive, AutoETS, AutoARIMA, LightGBM, and zero-shot Chronos-2, TimesFM 2.5, Moirai 2.0 small.

Same history, same horizon, 9 quantiles each.

**3/**
Each day's forecast file is SHA-256 hashed, listed in an append-only manifest, pushed to a public git branch and stamped with OpenTimestamps. All before the outcome exists.

Anyone can check the timing without trusting me.

**4/**
Scoring uses the first published value, not later revisions. Metrics: MASE, quantile CRPS, 80% interval coverage, skill vs seasonal naive with block bootstrap intervals over run dates.

**5/**
No model gets a rank until it has 28 days live and 10,000 scored forecasts. Until then the site says "no model is ranked yet".

**6/**
What is not new: live TSFM benchmarks exist (TS-Arena, Impermanent, LiveHouse-TS). My claim is narrower: Indian public series, hash-committed forecasts, and pip loaders that keep every data vintage.

**7/**
Limits: 2 sources, a few dozen series, one season so far. One fixed config per model on CPU. Mandi prices wait on a data.gov.in key.

**8/**
Model teams and anyone else can submit through a PR. It runs in Docker with no network.

Code and data branch: https://github.com/Tharun0127/Bhavishya

Critique of the method is welcome. Issues are open.
