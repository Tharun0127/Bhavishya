"""Statistical and machine learning baselines (Nixtla statsforecast and mlforecast)."""

from __future__ import annotations

from importlib.metadata import version
from typing import Any

import pandas as pd

from bhavishya.models.base import (
    LEVELS,
    Forecaster,
    ModelInfo,
    add_horizon,
    intervals_to_quantiles,
    to_nixtla,
)

SEASON = 7  # weekly seasonality: the dominant pattern in daily power demand and AQI


class _StatsForecastModel(Forecaster):
    """Shared wrapper: fit one local model per series and read central intervals as quantiles."""

    name: str
    model_col: str
    max_history_days = 730  # two years is plenty for these models and keeps AutoARIMA fast

    def _make(self) -> object:
        raise NotImplementedError

    def info(self) -> ModelInfo:
        return ModelInfo(
            name=self.name,
            family="baseline",
            version=f"statsforecast=={version('statsforecast')}",
            config={"model": self.model_col, "season_length": SEASON, "levels": LEVELS},
        )

    def _predict(self, history: pd.DataFrame, horizon: int) -> pd.DataFrame:
        from statsforecast import StatsForecast

        sf = StatsForecast(models=[self._make()], freq="D", n_jobs=1)
        fc = sf.forecast(df=to_nixtla(history), h=horizon, level=list(LEVELS))
        fc = fc.reset_index() if "unique_id" not in fc.columns else fc
        return add_horizon(intervals_to_quantiles(fc, self.model_col))


class SeasonalNaive(_StatsForecastModel):
    """Repeat the last observed week. The reference every other model is scored against."""

    name = "seasonal_naive"
    model_col = "SeasonalNaive"

    def _make(self) -> object:
        from statsforecast.models import SeasonalNaive as _SN

        return _SN(season_length=SEASON)


class AutoETS(_StatsForecastModel):
    name = "auto_ets"
    model_col = "AutoETS"

    def _make(self) -> object:
        from statsforecast.models import AutoETS as _ETS

        return _ETS(season_length=SEASON)


class AutoARIMA(_StatsForecastModel):
    name = "auto_arima"
    model_col = "AutoARIMA"

    def _make(self) -> object:
        from statsforecast.models import AutoARIMA as _ARIMA

        return _ARIMA(season_length=SEASON)


class LightGBMGlobal(Forecaster):
    """One LightGBM model across all series of a source, with conformal prediction intervals.

    Series are standardised per series so states of very different size can share one model.
    Intervals come from conformal calibration on the last few 28-day windows of history.
    """

    name = "lightgbm"
    max_history_days = 730
    # Each series and horizon is calibrated from up to this many errors. Three gave 80% intervals
    # that covered 43% of actuals in the pipeline test; more windows widen them toward nominal
    # coverage. Fewer are used when the shortest series cannot hold this many windows.
    conformal_windows = 10
    min_train_days = 90  # rows kept for training before the oldest window, after 28-day lags
    params: dict[str, Any] = {
        "n_estimators": 300,
        "learning_rate": 0.05,
        "num_leaves": 31,
        "min_child_samples": 20,
        "subsample": 0.9,
        "subsample_freq": 1,
        "colsample_bytree": 0.9,
        "random_state": 0,
        "verbose": -1,
        "n_jobs": 1,
    }

    def info(self) -> ModelInfo:
        return ModelInfo(
            name=self.name,
            family="baseline",
            version=f"mlforecast=={version('mlforecast')};lightgbm=={version('lightgbm')}",
            config={
                "params": self.params,
                "lags": [1, 7, 14, 21, 28],
                "max_conformal_windows": self.conformal_windows,
                "date_features": ["dayofweek", "month"],
                "levels": LEVELS,
            },
        )

    def _predict(self, history: pd.DataFrame, horizon: int) -> pd.DataFrame:
        from lightgbm import LGBMRegressor
        from mlforecast import MLForecast
        from mlforecast.lag_transforms import RollingMean
        from mlforecast.target_transforms import LocalStandardScaler
        from mlforecast.utils import PredictionIntervals

        mlf = MLForecast(
            models={"LGBM": LGBMRegressor(**self.params)},
            freq="D",
            lags=[1, 7, 14, 21, 28],
            lag_transforms={1: [RollingMean(window_size=7), RollingMean(window_size=28)]},
            date_features=["dayofweek", "month"],
            target_transforms=[LocalStandardScaler()],
        )
        data = to_nixtla(history)
        # Every series must hold the windows plus enough rows to train on before the oldest one.
        shortest = int(data.groupby("unique_id").size().min())
        windows = max(1, min(self.conformal_windows, (shortest - self.min_train_days) // horizon))
        mlf.fit(data, prediction_intervals=PredictionIntervals(n_windows=windows, h=horizon))
        fc = mlf.predict(horizon, level=list(LEVELS))
        return add_horizon(intervals_to_quantiles(fc, "LGBM"))
