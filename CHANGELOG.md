# Changelog

This project follows [Semantic Versioning](https://semver.org/). Before 1.0, minor versions may change the public API.

## 0.1.0 (unreleased)

- Loaders for Grid-India daily PSP reports, the CPCB daily AQI bulletin and Open-Meteo daily weather.
- Tidy output schema: `series_id, timestamp, value, unit, source, vintage_date`.
- Data contracts checked on every fetch.
- Vintage store with `as_of` and `first_release` views.
- Arena: model interface, baselines, foundation model wrappers, hashed forecast commits, scoring, leaderboard and static site.
