# Bhavishya

The live forecasting arena for India.

Bhavishya has two parts:

1. **A Python package** of clean, tested loaders for Indian public time series. Every row records the date the value was published (its vintage), so you can rebuild what was known on any past day.
2. **An arena.** Every day, baseline and foundation models forecast those series before the outcomes exist. Each day's forecast file is hashed and committed to git first. When the real values are published, the forecasts are scored automatically.

Start with [Usage](usage.md). Read [Methodology](METHODOLOGY.md) for the evaluation protocol and [Prior art](PRIOR_ART.md) for what is and is not new here.
