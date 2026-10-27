# Prior art for Bhavishya (IndiaCast Arena)

Research date: 2026-10-27. Sources were found through web search and, where noted, by opening the page. Anything we could not open or confirm is marked "unverified" or listed in section 7.

## 1. Summary

Live, prospective evaluation of time series foundation models (TSFMs) already exists. TS-Arena (energy, KDD 2026), Impermanent (GitHub activity, 2026) and LiveHouse-TS (17 datasets, August 2026) all ask models to forecast before the outcome exists and score them as data arrives. None of them that we found uses Indian public series, and none describes cryptographic commitment of forecasts (hashes in git, OpenTimestamps). Python wrappers for Indian public data exist for data.gov.in, Agmarknet, CPCB stations and IMD gridded weather, but we found no package that covers Grid-India daily power reports or CPCB daily AQI bulletins with vintage-dated raw snapshots. Our claim is therefore narrow: an open, prospective, hash-committed TSFM benchmark on Indian public series, paired with vintage-aware loaders.

## 2. Live and prospective forecasting benchmarks

"Live" means forecasts are made before the target value exists. "Static" means a fixed historical test split.

| Name | Link | What it does | Live or static | Domain | How we differ |
|---|---|---|---|---|---|
| TS-Arena (Meyer et al., arXiv 2512.20761, KDD 2026) | https://arxiv.org/abs/2512.20761, https://ts-arena.live/, https://github.com/DAG-UPB/ts-arena | Pre-registration platform. Submission windows close before ground truth is recorded; late submissions rejected. Elo-style ranking with bootstrap CIs. Paper reports 186 live series in 14 challenges. Data state archived with SCD2 in TimescaleDB. Reference track plus open track. | Live | Energy: SMARD (Germany), gridstatus (US ISOs), Fingrid (Finland) | Closest prior art. Paper says it scores point forecasts with MASE and that CRPS is not yet implemented (site now also shows a metric called "SQL", meaning unverified). Enforcement is by server-side windows, not public hashes. No Indian data. |
| Impermanent (Garza et al., arXiv 2603.08707) | https://arxiv.org/abs/2603.08707, https://github.com/TimeCopilot/impermanent, https://impermanent.timecopilot.dev | Sequential live evaluation on GitHub Archive series (stars, pushes, PRs, issues) for top 400 repos. MASE and scaled CRPS. Submissions by pull request. | Live | Software activity (one domain) | Different domain. README describes no hash or commitment mechanism. |
| LiveHouse-TS (Wen et al., arXiv 2608.17299) | https://arxiv.org/abs/2608.17299, https://huggingface.co/spaces/CityMindDev/LiveHouse-TS, https://github.com/zhouziyu02/TS-Live | "Living benchmark": 17 datasets from 15 public sources (Open-Meteo, NASA POWER, NOAA, USGS, Binance, Wikimedia, GDELT, others). CRPS from quantiles, rank, win rate, Elo, temporal stability. Outside models submitted as hosted HTTPS endpoints via GitHub issue. Raw responses archived with request metadata. | Live | 11 domains, mostly US or global sources | Uses Open-Meteo like us, but no Indian grid, AQI or mandi data in the visible text. No hash commitment described in the parts we read (appendix not fully read). |
| ForecastBench (Karger et al., ICLR 2025) | https://arxiv.org/abs/2409.19839, https://www.forecastbench.org/ | Auto-generated questions about unresolved future events, some from real-world time series; nightly resolution; public leaderboard with outside submissions. | Live | LLM judgmental forecasting | Targets LLMs answering questions, not numeric quantile forecasts from TSFMs. |
| Prophet Arena (arXiv 2510.17638, ICLR 2026) | https://arxiv.org/abs/2510.17638 | Live benchmark of LLMs on prediction-market events; accuracy, calibration, economic value. | Live | LLM event forecasting | Same distinction as ForecastBench. |
| FutureX (arXiv 2508.11987, ICLR 2026) | https://arxiv.org/abs/2508.11987 | Live benchmark for LLM agents predicting future events. Details not read. | Live | LLM agents | Same distinction. |
| FutureBench (Together AI, July 2025) | https://www.together.ai/blog/futurebench, https://huggingface.co/blog/futurebench | Agents forecast real-world events (markets, news) before they happen. Current status unverified. | Live | LLM agents | Same distinction. |
| Foresight Arena (arXiv 2605.00420) | https://arxiv.org/pdf/2605.00420 | On-chain commit-reveal: agent submits a salted hash of predictions before deadline, reveals later. Seen in search results only. | Live | AI forecasting agents (events) | Closest precedent for hash commitment, but for event forecasting, not TSFMs or Indian series. |
| M6 competition (Makridakis et al., IJF) | https://arxiv.org/abs/2310.13357 | Live financial forecasting and investment contest, Feb 2022 to Feb 2023, 100 assets. | Live (one-off, ended) | Finance | Finished competition, not an ongoing open leaderboard. |
| GEFCom 2012/2014/2017, BigDEAL 2018/2022 | https://en.wikipedia.org/wiki/Global_Energy_Forecasting_Competition, https://blog.drhongtao.com/search/label/competitions | Energy forecasting competitions (load, price, wind, solar), probabilistic tracks in 2014 and 2017. | Time-limited competitions. We did not confirm whether any track was strictly prospective. | Energy (US and other data) | Finished, time-boxed contests. No Indian data seen. |
| Fidel-TS (arXiv 2509.24789) | https://arxiv.org/abs/2509.24789 | Multimodal benchmark built from fresh data pulled from authenticated real-time APIs to avoid leakage. | Fresh data, but evaluated as a fixed benchmark (based on abstract) | Multimodal | Fresh collection, not continuous prospective scoring. |
| LEAF (arXiv 2605.16358) | https://arxiv.org/abs/2605.16358 | Living benchmark for event-augmented forecasting with LLMs. Abstract only. | Living | LLM plus events | Different model class. |
| Nixtla "arena" | https://github.com/Nixtla | We searched and found no Nixtla arena or live leaderboard. | Not found | n/a | n/a |

Also found: a user-run India AQI project (https://github.com/PaddyCH96/india-aqi-forecasting) that scores XGBoost against persistence on CPCB data with a dashboard. It is a single-model project, not an open multi-model prospective leaderboard (based on its description).

## 3. Static TSFM benchmarks and the contamination problem

| Name | Link | Notes |
|---|---|---|
| Monash Time Series Forecasting Archive (NeurIPS 2021) | https://arxiv.org/abs/2105.06643 | 20 to 25 public datasets (versions differ). Widely reused, so likely present in TSFM pretraining corpora. |
| GIFT-Eval (Salesforce, arXiv 2410.10393) | https://arxiv.org/abs/2410.10393, https://huggingface.co/spaces/Salesforce/GIFT-Eval | 23 datasets, 7 domains. Ships a separate non-leaking pretraining corpus (GiftEvalPretrain). |
| fev / fev-bench (AutoGluon/AWS, arXiv 2509.26468) | https://arxiv.org/abs/2509.26468, https://huggingface.co/spaces/autogluon/fev-bench, https://pypi.org/project/fev/ | 100 tasks, 46 with covariates. Win rate and skill score with bootstrap CIs. |
| BOOM (Datadog, arXiv 2505.14766) | https://arxiv.org/abs/2505.14766 | Observability benchmark from Datadog's own telemetry, released with the Toto model. |
| TIME (arXiv 2602.12147, ICML 2026) | https://arxiv.org/abs/2602.12147, https://huggingface.co/spaces/Real-TSF/TIME-leaderboard | 50 new datasets, 98 tasks, built for leakage-free zero-shot evaluation. Still a fixed split. |
| QuitoBench (arXiv 2603.26017) | https://arxiv.org/html/2603.26017 | Uses a proprietary source and a global temporal cutoff to avoid pretraining overlap (from search snippet). |
| Air Quality Arena (arXiv 2607.19381) | https://arxiv.org/abs/2607.19381, http://AirQualityArena.github.io | Static AQ benchmark, 7 countries including India (CPCB CAAQM portal), July 2022 to June 2025, 11 TSFMs incl. Chronos-2, TimesFM-2.5, Moirai-2. Most relevant static benchmark for our AQI track. |
| CaFE, "Beyond Static Leaderboards" (arXiv 2610.26251) | https://arxiv.org/abs/2610.26251 | Capability profiles via resampled GIFT-Eval and fev data. Static. |
| TimeSeriesExam (arXiv 2410.14752) | https://arxiv.org/abs/2410.14752 | Multiple-choice exam of LLM time series understanding. Not a forecasting benchmark. |
| TSFM.ai benchmark index | https://tsfm.ai/benchmarks | Third-party aggregator listing fev-bench, GIFT-Eval, BOOM, Impermanent, TIME, QuitoBench and others. |

The contamination problem is documented directly:

- Meyer et al., "Rethinking Evaluation in the Era of Time Series Foundation Models: (Un)known Information Leakage Challenges" (https://arxiv.org/abs/2510.13654) name two leakage types: reuse of the same datasets in training and testing, and temporal overlap between correlated training and test series.
- Pan and Ezzat (https://arxiv.org/abs/2607.02623) build a second, newer electricity price dataset specifically to reduce contamination risk when testing Chronos-2, TimesFM-2.5 and others.
- TSFMAudit (https://arxiv.org/pdf/2605.26161) audits contamination in forecasting TSFMs (seen in search results only).

Static benchmarks can reduce this risk with fresh or private data, but they cannot rule it out for models trained after the data was published. Prospective scoring can.

## 4. Indian public data loaders

| Name | Link | Source covered | Notes |
|---|---|---|---|
| datagovindia (PyPI 1.0.2) | https://pypi.org/project/datagovindia/, https://github.com/addypy/datagovindia | data.gov.in OGD APIs | Generic API wrapper. Needs a free API key. Not series-specific, no vintage snapshots described. |
| agmarknet (PyPI 0.2.2, uploaded 2026-07-14) | https://pypi.org/project/agmarknet/ | Official AGMARKNET REST API | Unofficial pandas client by Manojkumar Patil. Its listed GitHub homepage returned 404 when we checked. Overlaps our planned mandi loader. |
| imdlib (PyPI 0.4.0) | https://pypi.org/project/imdlib/ | IMD gridded rainfall and temperature | Weather alternative to Open-Meteo; Indian official source. |
| desidata (PyPI 0.1.1, uploaded 2026-10-26) | https://pypi.org/project/desidata/, https://github.com/krishnakaushik195/desidata-py | desidata.in curated catalogue | Loads curated Indian CSVs into pandas. Coverage of our sources unverified. |
| cpcbccr | https://github.com/sakethramanujam/cpcbccr-python-client, https://thejeshgn.com/2020/02/14/scraping-national-air-quality-data/ | CPCB CCR station data | README says `pip install cpcbccr`, but PyPI returned 404 for that name on 2026-10-27. Station-level, not the daily AQI bulletin. |
| openaq (PyPI 1.2.0) | https://pypi.org/project/openaq/ | OpenAQ, includes Indian stations | Official SDK. Air Quality Arena reports OpenAQ failed their continuity checks for most stations they assessed. |
| vayu (PyPI 0.0.214, last upload 2020) | https://pypi.org/project/vayu/, https://sustainability-lab.github.io/vayu | Air quality analysis and plotting | Visualization tool. Its page does not mention India or CPCB downloads. |
| Urbanemissions CPCB bulletin archive | https://urbanemissions.info/?p=4099 | CPCB daily bulletins 2015 to 2024 | Dataset, not a package. Useful for backfill and cross-checks. |
| grid-india-psp-tracker | https://github.com/rounakkar-collab/grid-india-psp-tracker | Grid-India PSP (inferred) | Small repo with `scraper.py` and scheduled workflows. Purpose not confirmed. |
| Daily India demand dataset (personal project) | https://jitendra.is-a.dev/me/projects/grid-load/ | npp.gov.in demand-met JSON | Daily-updating dataset via GitHub Actions and Kaggle (from search snippet). Different source from the PSP PDFs. |
| iancovert/Agmarknet | https://github.com/iancovert/Agmarknet | Agmarknet 2008 to 2017 | Static CSV dump, not a scraper. |
| CEDA Agmarknet (Ashoka University) | https://agmarknet.ceda.ashoka.edu.in/README.html | Agmarknet, cleaned | Research portal with downloads, not a package. |
| IndiaWeatherBench (arXiv 2509.00653) | https://arxiv.org/abs/2509.00653 | IMDAA reanalysis | Weather benchmark over India; authors say it does not yet support real-time forecasting. |

We found no package that loads Grid-India daily PSP reports or CPCB daily AQI bulletins as clean series while also keeping vintage-dated raw snapshots.

## 5. How this project differs

1. Data: Indian public series (Grid-India daily PSP, CPCB daily AQI bulletin, Open-Meteo for Indian locations, Agmarknet planned). The live benchmarks we found use German, US, Finnish, GitHub or mostly US/global sources.
2. Vintages: every raw download is stored with its retrieval date, so a forecast can be re-run against exactly the data that existed at forecast time. TS-Arena (SCD2 archive) and LiveHouse-TS (raw response archive) do something similar on the server side; ours ships in the pip package so users can do it themselves.
3. Public commitment: forecasts are SHA-256 hashed and committed to a public git repo, with OpenTimestamps proofs, before outcomes exist. Anyone can verify the timing without trusting our server. We found this pattern for event forecasting (Foresight Arena, on-chain) and in a F1000Research paper on OpenTimestamps for forecasts (https://f1000research.com/articles/15-1322, seen in search only), but not in a TSFM benchmark.
4. Probabilistic scoring: quantile forecasts scored with CRPS / weighted quantile loss and 80% interval coverage, alongside MASE and skill against seasonal naive. TS-Arena's paper scores point forecasts only; Impermanent and LiveHouse-TS do score CRPS.
5. Open submissions: outside forecasts accepted, as in TS-Arena, Impermanent and LiveHouse-TS.

## 6. Honest novelty claim

What is not new:

- Live or prospective forecasting benchmarks. TS-Arena, Impermanent and LiveHouse-TS do this for TSFMs; ForecastBench, Prophet Arena and FutureX do it for LLMs; M6 did it for finance.
- Live TSFM evaluation on energy data (TS-Arena).
- Using Open-Meteo in a live benchmark (LiveHouse-TS).
- Probabilistic live scoring with CRPS (Impermanent, LiveHouse-TS).
- Hash commit-reveal of forecasts in general (Foresight Arena for events).
- Python wrappers for some Indian public data (datagovindia, agmarknet, imdlib, cpcbccr).
- TSFM evaluation on Indian CPCB air quality data (Air Quality Arena, static).

What we can claim, based on what we found:

> To our knowledge, Bhavishya is the first open, prospective benchmark of time series foundation models on Indian public series (Grid-India power supply, CPCB AQI bulletins, Indian-location weather) where each forecast is SHA-256 hashed and committed to a public git repository, with OpenTimestamps proofs, before the outcome exists. It ships with pip-installable loaders that store vintage-dated raw snapshots of these sources. As far as we found, no existing Python package loads Grid-India daily PSP reports or CPCB daily AQI bulletins with vintage snapshots.

This claim rests on searches up to 2026-10-27. It should be rechecked before publication, since several close works appeared in 2026.

## 7. Things we could not verify

- Whether TS-Arena now scores quantile forecasts. The paper (v3, April 2026) says CRPS is not implemented; the live site shows a metric labelled "SQL" that we could not define.
- Full LiveHouse-TS dataset list and its appendix on data provenance. We read only part of the HTML. We did not see India, but did not confirm its absence.
- Impermanent's exact update cadence and whether it has any commitment mechanism beyond pipeline artifacts.
- Whether any GEFCom or BigDEAL track was strictly prospective, and whether any Kaggle competition ran live scoring on future data. We did not open primary sources on this.
- Nixtla: we found no "arena" or live TimeGPT leaderboard. It may exist under a name we did not search.
- "ProbCast" turned out to be an R package for producing and evaluating probabilistic forecasts (https://strathprints.strath.ac.uk/id/eprint/72822), not a benchmark.
- FutureBench (Together AI) current status and leaderboard.
- Foresight Arena, TSFMAudit and the F1000Research OpenTimestamps paper were seen in search results only, not opened.
- The `agmarknet` PyPI package's source repository (listed homepage returned 404) and its maintenance status.
- Whether `cpcbccr` was ever on PyPI (it is not now) and whether desidata covers our sources.
- The purpose of grid-india-psp-tracker and other small GitHub repos found by name only.
- A Frontiers 2026 paper on a temporally validated AQI benchmark for Indian cities (https://www.frontiersin.org/journals/environmental-science/articles/10.3389/fenvs.2026.1952221/full), seen in search only.

## PyPI name availability (checked 2026-10-27 via https://pypi.org/pypi/NAME/json)

| Name | Result |
|---|---|
| bhavishya | 404, free |
| indiacast | 404, free |
| india-cast | 404, free |
| bhavishya-arena | 404, free |

Names can be taken at any time. Register early if the name matters.
