"""Which models run in the arena, in which Python environment, with what time limit."""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from bhavishya.models.base import Forecaster


@dataclass(frozen=True)
class ModelSpec:
    name: str
    target: str  # "module:Class"
    env: str = "main"  # "main", "moirai", or "docker" for submissions
    timeout_s: int = 1800

    def load(self) -> Forecaster:
        module, cls = self.target.split(":")
        return getattr(importlib.import_module(module), cls)()


MODELS: dict[str, ModelSpec] = {
    m.name: m
    for m in (
        ModelSpec("seasonal_naive", "bhavishya.models.baselines:SeasonalNaive", timeout_s=600),
        ModelSpec("auto_ets", "bhavishya.models.baselines:AutoETS"),
        ModelSpec("auto_arima", "bhavishya.models.baselines:AutoARIMA"),
        ModelSpec("lightgbm", "bhavishya.models.baselines:LightGBMGlobal"),
        ModelSpec("chronos2", "bhavishya.models.foundation:Chronos2"),
        ModelSpec("timesfm2_5", "bhavishya.models.foundation:TimesFM25"),
        ModelSpec("moirai2", "bhavishya.models.foundation:Moirai2", env="moirai"),
    )
}

#: Every score is relative to this model.
REFERENCE_MODEL = "seasonal_naive"


def python_for(env: str) -> str:
    """Interpreter for an environment. CI sets BHAVISHYA_PYTHON_<ENV>; locally we look for .venv-<env>."""
    if env == "main":
        return sys.executable
    override = os.environ.get(f"BHAVISHYA_PYTHON_{env.upper()}")
    if override:
        return override
    root = Path(os.environ.get("BHAVISHYA_REPO_ROOT", Path.cwd()))
    for candidate in (
        root / f".venv-{env}" / "Scripts" / "python.exe",
        root / f".venv-{env}" / "bin" / "python",
    ):
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(f"no Python found for environment {env!r}; set BHAVISHYA_PYTHON_{env.upper()}")
