"""Zero-shot time series foundation models, pinned to exact Hugging Face revisions.

Revisions were the latest commits on 2026-10-27. The SHA-256 of the weights file is computed
on every run and stored with the forecasts, so a silent change of weights would be visible.
"""

from __future__ import annotations

from importlib.metadata import version

import numpy as np
import pandas as pd

from bhavishya.models.base import QUANTILE_COLUMNS, QUANTILES, Forecaster, ModelInfo, hf_weights

CHRONOS2_REPO, CHRONOS2_REV = "amazon/chronos-2", "29ec3766d36d6f73f0696f85560a422f50e8498c"
TIMESFM_REPO, TIMESFM_REV = "google/timesfm-2.5-200m-pytorch", "1d952420fba87f3c6dee4f240de0f1a0fbc790e3"
MOIRAI2_REPO, MOIRAI2_REV = "Salesforce/moirai-2.0-R-small", "30f43ff08c8494f4943ae1521e9d4e94a0fbb389"

CONTEXT = 1024  # days of context given to every foundation model


def _series_arrays(history: pd.DataFrame) -> tuple[list[str], list[np.ndarray]]:
    ids, arrays = [], []
    for sid, part in history.sort_values("timestamp").groupby("series_id", sort=True):
        ids.append(str(sid))
        arrays.append(part["value"].to_numpy(dtype="float64")[-CONTEXT:])
    return ids, arrays


def _stack(ids: list[str], quantiles: np.ndarray, horizon: int) -> pd.DataFrame:
    """``quantiles`` has shape (n_series, horizon, 9)."""
    frames = []
    for i, sid in enumerate(ids):
        part = pd.DataFrame(quantiles[i, :horizon, :], columns=list(QUANTILE_COLUMNS))
        part.insert(0, "horizon", np.arange(1, horizon + 1))
        part.insert(0, "series_id", sid)
        frames.append(part)
    return pd.concat(frames, ignore_index=True)


class Chronos2(Forecaster):
    name = "chronos2"
    max_history_days = CONTEXT

    def __init__(self) -> None:
        self._path, self._sha = hf_weights(CHRONOS2_REPO, CHRONOS2_REV)

    def info(self) -> ModelInfo:
        return ModelInfo(
            self.name,
            "foundation",
            f"chronos-forecasting=={version('chronos-forecasting')}",
            CHRONOS2_REPO,
            CHRONOS2_REV,
            self._sha,
            {"context": CONTEXT, "cross_learning": False},
        )

    def _predict(self, history: pd.DataFrame, horizon: int) -> pd.DataFrame:
        import torch
        from chronos import Chronos2Pipeline

        torch.manual_seed(0)
        pipe = Chronos2Pipeline.from_pretrained(CHRONOS2_REPO, revision=CHRONOS2_REV, device_map="cpu")
        df = history.rename(columns={"series_id": "item_id", "value": "target"})
        fc = pipe.predict_df(
            df,
            prediction_length=horizon,
            quantile_levels=list(QUANTILES),
            id_column="item_id",
            timestamp_column="timestamp",
            target="target",
        )
        fc = fc.sort_values(["item_id", "timestamp"])
        out = pd.DataFrame({"series_id": fc["item_id"].astype(str).to_numpy()})
        for q, col in zip(QUANTILES, QUANTILE_COLUMNS, strict=True):
            out[col] = fc[str(q)].to_numpy()
        out["horizon"] = out.groupby("series_id").cumcount() + 1
        return out


class TimesFM25(Forecaster):
    name = "timesfm2_5"
    max_history_days = CONTEXT

    def __init__(self) -> None:
        self._path, self._sha = hf_weights(TIMESFM_REPO, TIMESFM_REV)

    def info(self) -> ModelInfo:
        return ModelInfo(
            self.name,
            "foundation",
            f"timesfm=={version('timesfm')}",
            TIMESFM_REPO,
            TIMESFM_REV,
            self._sha,
            {"context": CONTEXT, "use_continuous_quantile_head": True},
        )

    def _predict(self, history: pd.DataFrame, horizon: int) -> pd.DataFrame:
        import timesfm
        import torch

        torch.manual_seed(0)
        model = timesfm.TimesFM_2p5_200M_torch.from_pretrained(TIMESFM_REPO, revision=TIMESFM_REV)
        model.compile(
            timesfm.ForecastConfig(
                max_context=CONTEXT,
                max_horizon=128,
                normalize_inputs=True,
                use_continuous_quantile_head=True,
                fix_quantile_crossing=True,
            )
        )
        ids, arrays = _series_arrays(history)
        _, q = model.forecast(horizon=horizon, inputs=arrays)
        # TimesFM returns [mean, q0.1, ..., q0.9] in the last axis.
        return _stack(ids, np.asarray(q)[:, :, 1:10], horizon)


class Moirai2(Forecaster):
    """Runs only inside the Moirai environment (.venv-moirai). See docs/DECISIONS.md D4."""

    name = "moirai2"
    max_history_days = CONTEXT

    def __init__(self) -> None:
        self._path, self._sha = hf_weights(MOIRAI2_REPO, MOIRAI2_REV)

    def info(self) -> ModelInfo:
        return ModelInfo(
            self.name,
            "foundation",
            f"uni2ts=={version('uni2ts')}",
            MOIRAI2_REPO,
            MOIRAI2_REV,
            self._sha,
            {"context": CONTEXT},
        )

    def _predict(self, history: pd.DataFrame, horizon: int) -> pd.DataFrame:
        import torch
        from uni2ts.model.moirai2 import Moirai2Forecast, Moirai2Module

        torch.manual_seed(0)
        module = Moirai2Module.from_pretrained(MOIRAI2_REPO, revision=MOIRAI2_REV)
        model = Moirai2Forecast(
            module=module,
            prediction_length=horizon,
            context_length=CONTEXT,
            target_dim=1,
            feat_dynamic_real_dim=0,
            past_feat_dynamic_real_dim=0,
        )
        ids, arrays = _series_arrays(history)
        pred = model.predict(past_target=[a[:, None] for a in arrays])  # (n, 9, horizon)
        return _stack(ids, np.transpose(np.asarray(pred), (0, 2, 1)), horizon)
