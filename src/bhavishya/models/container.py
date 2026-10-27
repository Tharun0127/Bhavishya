"""Entry point inside a submission container.

Loads the class named in ``/app/model.yaml`` (``entrypoint: forecast.py:MyModel``), runs it on
the mounted history file, and writes forecasts to ``/output``. There is no network here.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pandas as pd
import yaml

from bhavishya.models.base import HORIZON, Forecaster


def load_entrypoint(app: Path) -> Forecaster:
    meta = yaml.safe_load((app / "model.yaml").read_text(encoding="utf-8"))
    file_name, cls_name = str(meta["entrypoint"]).split(":")
    spec = importlib.util.spec_from_file_location("submission_model", app / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {file_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = getattr(module, cls_name)()
    if not isinstance(model, Forecaster):
        raise TypeError(f"{cls_name} must subclass bhavishya.models.base.Forecaster")
    return model


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--history", required=True)
    p.add_argument("--cutoff", required=True)
    p.add_argument("--horizon", type=int, default=HORIZON)
    p.add_argument("--out", required=True)
    p.add_argument("--app", default="/app")
    args = p.parse_args(argv)
    model = load_entrypoint(Path(args.app))
    history = pd.read_parquet(args.history)
    model.forecast(history, pd.Timestamp(args.cutoff), args.horizon).to_parquet(args.out, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
