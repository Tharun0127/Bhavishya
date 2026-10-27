"""Template submission: a seasonal mean of the last four weeks.

Replace `_predict` with your model. Rules:
- You receive `history` with columns series_id, timestamp, value. It ends at the cutoff.
- Return columns series_id, horizon (1..H), q0.1 ... q0.9 for every series and horizon.
- There is no network at forecast time. Download weights in the Dockerfile.
"""

from __future__ import annotations

import pandas as pd

from bhavishya.models.base import QUANTILE_COLUMNS, Forecaster, ModelInfo


class MyModel(Forecaster):
    def info(self) -> ModelInfo:
        return ModelInfo(name="my_model", family="submission", version="0.1.0")

    def _predict(self, history: pd.DataFrame, horizon: int) -> pd.DataFrame:
        rows = []
        for sid, part in history.groupby("series_id"):
            values = part["value"].to_numpy()[-28:]
            for h in range(1, horizon + 1):
                same_weekday = values[(h - 1) % 7 :: 7]  # values on the same weekday as the target
                qs = pd.Series(same_weekday).quantile([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]).to_numpy()
                rows.append({"series_id": sid, "horizon": h, **dict(zip(QUANTILE_COLUMNS, qs))})
        return pd.DataFrame(rows)
