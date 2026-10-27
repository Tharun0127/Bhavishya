"""Outside model submissions: metadata checks and a sandboxed Docker run.

Every submission runs in a container with no network, a memory and CPU cap, a process cap, a
read-only root filesystem and a wall-clock limit. Only the history file is mounted, read-only.
The host process (trusted code) validates the output with the same checks as built-in models.
See SECURITY.md for the threat model.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from bhavishya.models.base import HORIZON, finalize_forecast

REQUIRED = ("name", "version", "authors", "licence", "weights_source", "entrypoint", "description")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")

#: Limits for one container run. Kept below a standard GitHub-hosted runner (4 CPU, 16 GB).
LIMITS: dict[str, str] = {"memory": "6g", "cpus": "2", "pids": "256"}
TIMEOUT_S = 1800


@dataclass(frozen=True)
class Submission:
    path: Path
    meta: dict[str, object]

    @property
    def name(self) -> str:
        return str(self.meta["name"])

    @property
    def image(self) -> str:
        return f"bhavishya-sub-{self.name}:{self.meta['version']}"


def load_submission(path: Path) -> Submission:
    """Read and validate ``model.yaml``. Raises ``ValueError`` listing every problem."""
    meta = yaml.safe_load((path / "model.yaml").read_text(encoding="utf-8")) or {}
    problems = [f"missing field {k!r}" for k in REQUIRED if not meta.get(k)]
    if meta.get("name") and not NAME_RE.match(str(meta["name"])):
        problems.append("name must be 3-41 chars of lower-case letters, digits and underscores")
    if meta.get("name") and meta["name"] != path.name:
        problems.append("name must match the folder name")
    if not (path / "Dockerfile").exists():
        problems.append("Dockerfile missing")
    if problems:
        raise ValueError(f"{path}: " + "; ".join(problems))
    return Submission(path, meta)


def docker_build(sub: Submission) -> None:
    # Network is allowed at build time (installing packages, downloading weights) but not at run time.
    subprocess.run(["docker", "build", "--pull", "-t", sub.image, str(sub.path)], check=True, timeout=3600)


def docker_forecast(sub: Submission, history: Path, cutoff: pd.Timestamp, out_dir: Path) -> pd.DataFrame:
    """Run the container on one history file and return validated forecasts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "container_out"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--memory", LIMITS["memory"], "--memory-swap", LIMITS["memory"],
        "--cpus", LIMITS["cpus"], "--pids-limit", LIMITS["pids"],
        "--read-only", "--tmpfs", "/tmp:rw,size=512m",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "-v", f"{history.resolve()}:/input/history.parquet:ro",
        "-v", f"{work.resolve()}:/output:rw",
        sub.image,
        "--history", "/input/history.parquet", "--cutoff", f"{cutoff:%Y-%m-%d}",
        "--horizon", str(HORIZON), "--out", "/output/forecasts.parquet",
    ]  # fmt: skip
    subprocess.run(cmd, check=True, timeout=TIMEOUT_S, capture_output=True)
    raw = pd.read_parquet(work / "forecasts.parquet")
    expected = sorted(pd.read_parquet(history)["series_id"].unique())
    # Re-validate on the host: never trust the container's own checks.
    return finalize_forecast(
        raw.drop(columns=["cutoff", "target_date"], errors="ignore"), cutoff, HORIZON, expected
    )


def run_submission(root: Path, path: Path, run_date: pd.Timestamp, build: bool = True) -> dict[str, str]:
    """Run a submission on every prepared source and stage its output like a built-in model."""
    sub = load_submission(path)
    if build:
        docker_build(sub)
    inputs = root / "inputs" / f"{run_date:%Y-%m-%d}"
    prepared = json.loads((inputs / "prepared.json").read_text(encoding="utf-8"))
    stage = root / "staging" / f"{run_date:%Y-%m-%d}" / sub.name
    stage.mkdir(parents=True, exist_ok=True)
    status: dict[str, str] = {}
    for source, cutoff in prepared["cutoffs"].items():
        try:
            fc = docker_forecast(sub, inputs / f"{source}.parquet", pd.Timestamp(cutoff), stage)
            fc.to_parquet(stage / f"{source}.parquet", index=False)
            info = {
                "name": sub.name,
                "family": "submission",
                "version": str(sub.meta["version"]),
                "authors": sub.meta["authors"],
                "licence": sub.meta["licence"],
                "weights_source": sub.meta["weights_source"],
                "image": sub.image,
            }
            (stage / f"{source}.json").write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
            status[source] = "ok"
        except Exception as exc:  # a failing submission is recorded, never fatal
            status[source] = f"failed: {exc!r}"[:500]
    (stage / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


def list_submissions(folder: Path = Path("submissions")) -> list[Path]:
    return (
        sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("_"))
        if folder.exists()
        else []
    )
