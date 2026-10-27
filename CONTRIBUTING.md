# Contributing

Thanks for helping. There are three ways to contribute.

## 1. Enter a model in the arena

### The contract

A submission is a folder `submissions/<model_name>/` with:

| File | Purpose |
|---|---|
| `model.yaml` | name, version, authors, licence, weights source, entrypoint, description |
| `forecast.py` | a class that subclasses `bhavishya.models.base.Forecaster` |
| `requirements.txt` | pinned dependencies |
| `Dockerfile` | builds the image; downloads any weights at build time |

Your class implements one method:

```python
def _predict(self, history: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """history: series_id, timestamp, value (daily, no gaps, ends at the cutoff).
    Return: series_id, horizon (1..horizon), q0.1, q0.2, ..., q0.9 for every series and horizon."""
```

and `info()`, returning a `ModelInfo`. The base class checks that history ends at the cutoff, that every series and horizon is present, and that values are finite. Quantiles are sorted if they cross.

### Rules

- **No network when forecasting.** The container runs with `--network none`. Download weights in the `Dockerfile`.
- **Limits per run:** 2 CPUs, 6 GB memory, 256 processes, 30 minutes, read-only filesystem except `/tmp` and `/output`.
- **Licence:** your code and weights must allow us to run them and publish the forecasts.
- **Honest training data:** say in `description` whether the model was trained or tuned on any data after 2026-10-27. Models trained on the evaluation period are labelled as such.
- **No look-ahead:** you get only the history file. Do not try to fetch data inside the container.

### Steps

1. Copy `submissions/_template/` to `submissions/<model_name>/` and edit it.
2. Test without Docker:

   ```bash
   pip install -e ".[arena]"
   python -c "
   import pandas as pd, sys; sys.path.insert(0, 'submissions/<model_name>')
   from forecast import MyModel
   h = pd.read_parquet('arena-data/inputs/<date>/grid_india.parquet')
   print(MyModel().forecast(h, h.timestamp.max()).head())"
   ```

3. Test with Docker, as CI will: `bhavishya run-submission --path submissions/<model_name> --run-date <date>`.
4. Open a pull request. A maintainer reads the code, then applies the `run-submission` label. CI builds and runs it once on the latest inputs and uploads the output.
5. After merge, the model runs every day with the others. Its days live start counting from its first committed forecast. Past days are never backfilled.

## 2. Improve the data package

- New sources need: a public source whose terms allow reuse, a loader with a data contract, recorded fixtures, and an entry in `DATA_SOURCES.md`.
- Run `ruff check src tests`, `ruff format src tests`, `mypy` and `pytest` before opening a PR.

## 3. Critique the methodology

Open an issue. Changes to scoring or the panel apply to new panel versions only. Results are never rescored silently.
