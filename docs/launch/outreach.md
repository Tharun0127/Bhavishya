# DRAFTS NOT SENT: individual outreach messages

Every message below is a draft. None has been sent. Do not send any of them before the leaderboard is public and the facts in them are still true on the day of sending. Replace https://tharun0127.github.io/Bhavishya/ and check each team's current contact route (GitHub issue, discussion forum or public email listed in their repository). Do not use private addresses found elsewhere.

Each message is 120 to 200 words, says what we run of theirs, how to submit an improved configuration, and asks one question.

---

## 1. Amazon Chronos team (DRAFT, NOT SENT)

Suggested route: a GitHub Discussion on the chronos-forecasting repository.

Subject: Chronos-2 in a live arena on Indian power and AQI data

Hello,

I maintain Bhavishya, an open arena that forecasts Indian public data before it is published: Grid-India daily energy met by state and CPCB daily city AQI. Forecasts are hashed and committed to git with OpenTimestamps before outcomes exist, then scored against first-released values (MASE, quantile CRPS, 80% coverage, skill against seasonal naive).

We run Chronos-2 zero-shot, revision 29ec3766 of amazon/chronos-2, through `Chronos2Pipeline.predict_df` on CPU, with 1,024 days of context, nine quantiles 0.1 to 0.9, 28-day horizon, and no covariates or cross-series learning. The arena started on 27 October 2026, so there are no results yet.

If you think a different configuration is fairer, you can submit it as a separate entry through a pull request (template in `submissions/_template/`). It runs in a Docker sandbox with no network.

One question: for daily univariate series with strong weekly patterns, would you expect enabling cross-learning across states in one batch to help or hurt Chronos-2?

Code: https://github.com/Tharun0127/Bhavishya
Leaderboard: https://tharun0127.github.io/Bhavishya/

Tharun0127

---

## 2. Google TimesFM team (DRAFT, NOT SENT)

Suggested route: a GitHub issue or discussion on the timesfm repository.

Subject: TimesFM 2.5 in a live arena on Indian public data

Hello,

I maintain Bhavishya, an open arena where models forecast Indian public data (Grid-India daily state energy met, CPCB daily city AQI) before it is published. Each day's forecast file is SHA-256 hashed and committed to a public git branch with an OpenTimestamps proof, then scored against first-released values.

We run TimesFM 2.5 200M (google/timesfm-2.5-200m-pytorch, revision 1d952420) on CPU with `max_context=1024`, `normalize_inputs=True`, `use_continuous_quantile_head=True`, `fix_quantile_crossing=True`, and take q0.1 to q0.9 from the quantile output. Horizon is 28 days. There are no results yet; the arena started on 27 October 2026.

We did not include TimesFM 3.0 because of its licence and because its code was not on PyPI at launch. If that changes, or if you prefer a different 2.5 configuration, a pull request with a submission folder is the route. It runs sandboxed with no network.

One question: is slicing indices 1 to 9 of the quantile output the correct way to read q0.1 to q0.9 in version 2.5?

Code: https://github.com/Tharun0127/Bhavishya
Leaderboard: https://tharun0127.github.io/Bhavishya/

Tharun0127

---

## 3. Salesforce Moirai / uni2ts team (DRAFT, NOT SENT)

Suggested route: a GitHub Discussion on the uni2ts repository.

Subject: Moirai 2.0 small in a live arena on Indian public data

Hello,

I maintain Bhavishya, an open arena that forecasts Grid-India daily state energy met and CPCB daily city AQI before the values are published. Forecasts are hashed, committed to git with OpenTimestamps, and scored against first-released values with quantile CRPS, MASE and 80% coverage.

We run Moirai 2.0 small (Salesforce/moirai-2.0-R-small, revision 30f43ff0) zero-shot through `Moirai2Forecast` on CPU, with 1,024 days of context, 28-day horizon, univariate, no covariates. Because uni2ts pins `torch<2.5`, `numpy~=1.26` and `scipy~=1.11`, it runs in its own Python 3.11 environment and CI job. There are no results yet; the arena started on 27 October 2026.

If you want a different configuration or a larger checkpoint evaluated, you can submit it as a separate entry through a pull request. It runs in a Docker sandbox with no network.

One question: are the uni2ts dependency pins expected to be relaxed in a coming release, so Moirai can share an environment with current PyTorch?

Code: https://github.com/Tharun0127/Bhavishya
Leaderboard: https://tharun0127.github.io/Bhavishya/

Tharun0127

---

## 4. Nixtla team (DRAFT, NOT SENT)

Suggested route: Nixtla community Slack or a GitHub Discussion on statsforecast.

Subject: statsforecast and mlforecast baselines in a live Indian forecasting arena

Hello,

I maintain Bhavishya, an open arena where models forecast Indian public data (Grid-India daily state energy met, CPCB daily city AQI) before publication. Forecast files are hashed and committed to git with OpenTimestamps before outcomes exist.

Four of the seven models use your libraries. statsforecast gives seasonal naive (the reference for all skill scores), AutoETS and AutoARIMA, each with season length 7 and intervals at 20, 40, 60 and 80% mapped to nine quantiles. mlforecast gives a global LightGBM with lags 1, 7, 14, 21, 28, rolling means, day of week and month, `LocalStandardScaler`, and conformal intervals from three 28-day windows. There are no results yet; the arena started on 27 October 2026.

If you would configure these differently, for example MSTL or a TimeGPT entry, a pull request with a submission folder is the route. Submissions run with no network at forecast time.

One question: with only three conformal windows per series, would you recommend more windows, or a different interval method, for daily series about two years long?

Code: https://github.com/Tharun0127/Bhavishya
Leaderboard: https://tharun0127.github.io/Bhavishya/

Tharun0127

---

## 5. Indian agritech: a marketplace that uses mandi prices (generic, DRAFT, NOT SENT)

For: an agritech marketplace that sets or displays prices using Agmarknet mandi data. No specific company or contact is named here. Find a public contact route before adapting this.

Subject: open benchmark for mandi price forecasts (planned)

Hello,

I maintain Bhavishya, an open arena that forecasts Indian public data before it is published and scores the forecasts publicly. Today it covers Grid-India power data and CPCB city AQI. Every forecast is hashed and committed to git before the outcome exists, so the timing can be checked by anyone.

Agmarknet mandi prices are the next planned source. They are deferred until I have a data.gov.in API key, and history would be built from daily snapshots because the resource returns current prices only.

We do not run any model of yours. If your team forecasts mandi prices, you could later enter a model through a pull request. It runs in a sandbox with no network, and only its forecasts and scores are published. There are no results yet for any source.

One question: which forecast horizon matters most for your pricing decisions, next day, next week, or next month?

Code: https://github.com/Tharun0127/Bhavishya
Leaderboard: https://tharun0127.github.io/Bhavishya/

Tharun0127

---

## 6. Indian agritech: farm advisory or input supply (generic, DRAFT, NOT SENT)

For: a company that advises farmers on when and where to sell, or plans input supply. No specific company or contact is named here.

Subject: question about price forecast needs for farm advisory

Hello,

I maintain Bhavishya, an open, public arena where forecasting models predict Indian public data before it is released. Forecasts are hashed and committed to git first, then scored against the first published value with probabilistic metrics (quantile CRPS and interval coverage), not only point error.

Today the arena covers Grid-India power and CPCB AQI. Agmarknet mandi prices are planned once I have a data.gov.in API key. We do not run any model of yours.

If you forecast arrivals or modal prices, you could later enter a model through a pull request. It runs in a sandbox with no network, and you keep your code under the licence you choose. There are no results yet.

One question: for advisory messages to farmers, do you use a single expected price or a price range, and how wide a range is still useful to a farmer?

Code: https://github.com/Tharun0127/Bhavishya
Leaderboard: https://tharun0127.github.io/Bhavishya/

Tharun0127

---

## 7. Indian agritech: commodity trading or warehouse finance (generic, DRAFT, NOT SENT)

For: a firm that finances stored produce or trades commodities using mandi price data. No specific company or contact is named here.

Subject: open, timestamped benchmark for mandi price forecasts (planned)

Hello,

I maintain Bhavishya, an open arena that scores forecasts of Indian public data made before the data is published. Each day's forecasts are SHA-256 hashed, committed to a public git branch and timestamped with OpenTimestamps, so nobody can change them after the outcome is known.

It currently covers Grid-India power and CPCB AQI. Agmarknet mandi prices are planned once a data.gov.in key is in place. We do not run any model of yours, and there are no results yet.

If your team forecasts prices for collateral or trading, you could later enter a model through a pull request. It runs in a sandbox with no network. Only forecasts and scores are published.

One question: when prices are revised or a mandi reports late, which value do you treat as the outcome, the first reported price or a later corrected one?

Code: https://github.com/Tharun0127/Bhavishya
Leaderboard: https://tharun0127.github.io/Bhavishya/

Tharun0127

---

## 8. Indian energy analytics firm: demand forecasting (generic, DRAFT, NOT SENT)

For: a firm that forecasts state or discom electricity demand for utilities or traders. No specific company or contact is named here.

Subject: live public benchmark on Grid-India daily state energy met

Hello,

I maintain Bhavishya, an open arena where models forecast Grid-India daily energy met, nationally and for 15 states, 1 to 28 days ahead, before the report is published. Each day's forecast file is hashed and committed to git with an OpenTimestamps proof. Scores use the first-released value: MASE, quantile CRPS, 80% coverage, and skill against seasonal naive with bootstrap intervals.

Seven models run today: seasonal naive, AutoETS, AutoARIMA, LightGBM, Chronos-2, TimesFM 2.5 and Moirai 2.0 small. We do not run any model of yours. There are no results yet; it started on 27 October 2026.

If you want to test a model publicly, you can submit it through a pull request. It runs in a sandbox with no network. You can keep weights private by baking them into the image, as long as the licence lets us run it and publish forecasts.

One question: how often do Grid-India's daily state figures get revised after first release, in your experience?

Code: https://github.com/Tharun0127/Bhavishya
Leaderboard: https://tharun0127.github.io/Bhavishya/

Tharun0127

---

## 9. Indian energy analytics firm: renewables and market analytics (generic, DRAFT, NOT SENT)

For: a firm that provides power market or renewable integration analytics. No specific company or contact is named here.

Subject: question on useful targets for a public Indian power forecasting benchmark

Hello,

I maintain Bhavishya, an open arena that forecasts Indian public data before it is published, then scores it against first-released values. Forecasts are hashed and committed to a public git branch with OpenTimestamps, so their timing can be verified.

On the power side it covers Grid-India daily energy met by state and all-India maximum demand, from the daily PSP report. We do not run any model of yours. There are no results yet; it started on 27 October 2026.

If you would like to enter a model, the route is a pull request with a submission folder. It runs sandboxed with no network, and only forecasts and scores are published.

One question: which daily series in the PSP report, other than energy met, would be most useful to forecast publicly, for example peak shortage, solar or wind generation, or regional demand?

Code: https://github.com/Tharun0127/Bhavishya
Leaderboard: https://tharun0127.github.io/Bhavishya/

Tharun0127
