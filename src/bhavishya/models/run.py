"""Model worker. Runs one model in its own process on one history file.

    python -m bhavishya.models.run --model chronos2 --history in.parquet --cutoff 2026-10-26 \
        --out forecasts.parquet --info info.json

The worker only ever sees the history file it is given. That file is written by the arena
after truncating at the cutoff, so the model process has no path to later data.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict

import pandas as pd

from bhavishya.models.base import HORIZON, Forecaster


def run_model(
    model: Forecaster, history_path: str, cutoff: str, horizon: int, out: str, info_path: str
) -> None:
    history = pd.read_parquet(history_path)
    start = time.perf_counter()
    forecasts = model.forecast(history, pd.Timestamp(cutoff), horizon)
    elapsed = time.perf_counter() - start
    forecasts.to_parquet(out, index=False)
    info = asdict(model.info())
    info["config_hash"] = model.info().config_hash()
    info["seconds"] = round(elapsed, 2)
    info["n_series"] = int(history["series_id"].nunique())
    with open(info_path, "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=2, sort_keys=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--history", required=True)
    p.add_argument("--cutoff", required=True)
    p.add_argument("--horizon", type=int, default=HORIZON)
    p.add_argument("--out", required=True)
    p.add_argument("--info", required=True)
    args = p.parse_args(argv)

    from bhavishya.models.registry import MODELS

    run_model(MODELS[args.model].load(), args.history, args.cutoff, args.horizon, args.out, args.info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
