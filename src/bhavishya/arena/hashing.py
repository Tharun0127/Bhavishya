"""Tamper evidence: SHA-256 manifest of forecast files, plus OpenTimestamps proofs.

The manifest is an append-only CSV on the data branch. Each line names a forecast file and its
hash. The line is committed and pushed before any outcome for that file's horizons exists.
Changing a forecast later would change its hash and contradict the git history (and the
OpenTimestamps proof, which anchors the hash in the Bitcoin blockchain via public calendars).
"""

from __future__ import annotations

import csv
import hashlib
import os
from pathlib import Path

import pandas as pd

MANIFEST_FIELDS = ("run_date", "path", "sha256", "n_rows", "models", "created_at_utc")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def append_manifest(root: Path, row: dict[str, object]) -> None:
    path = root / "manifest.csv"
    new = not path.exists()
    if not new and str(row["path"]) in set(read_manifest(root)["path"]):
        raise FileExistsError(f"{row['path']} is already in the manifest; forecasts are append-only")
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in MANIFEST_FIELDS})


def read_manifest(root: Path) -> pd.DataFrame:
    path = root / "manifest.csv"
    if not path.exists():
        return pd.DataFrame(columns=list(MANIFEST_FIELDS))
    return pd.read_csv(path, dtype=str)


def verify_manifest(root: Path) -> list[str]:
    """Recompute every hash. Returns a list of problems (empty means all files match)."""
    problems = []
    for row in read_manifest(root).itertuples():
        path = root / str(row.path)
        if not path.exists():
            problems.append(f"{row.path}: missing")
        elif sha256_file(path) != row.sha256:
            problems.append(f"{row.path}: hash mismatch")
    return problems


#: Public calendars run by the OpenTimestamps project. Two, so one outage does not lose the stamp.
CALENDARS = ("https://a.pool.opentimestamps.org", "https://b.pool.opentimestamps.org")


def ots_stamp(path: Path, calendars: tuple[str, ...] = CALENDARS) -> Path | None:
    """Write ``<path>.ots``: the file's SHA-256 submitted to public OpenTimestamps calendars.

    We use the ``opentimestamps`` library directly instead of the ``ots`` command, because the
    command needs OpenSSL through ctypes and fails on Windows. The resulting file is a standard
    proof that anyone can check with ``ots verify``. A failed stamp never blocks the forecast
    commit: the git commit and the manifest hash are the primary record.
    """
    try:
        from opentimestamps.calendar import RemoteCalendar
        from opentimestamps.core.op import OpAppend, OpSHA256
        from opentimestamps.core.serialize import StreamSerializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile
    except ImportError:
        return None
    with path.open("rb") as fh:
        detached = DetachedTimestampFile.from_fd(OpSHA256(), fh)
    # A random nonce keeps the calendar from learning the file hash itself.
    tip = detached.timestamp.ops.add(OpAppend(os.urandom(16))).ops.add(OpSHA256())
    stamped = 0
    for url in calendars:
        try:
            tip.merge(RemoteCalendar(url).submit(tip.msg, timeout=30))
            stamped += 1
        except Exception:  # network or calendar error: try the next calendar
            continue
    if not stamped:
        return None
    proof = path.with_name(path.name + ".ots")
    with proof.open("wb") as fh:
        detached.serialize(StreamSerializationContext(fh))
    return proof


def ots_upgrade(proof: Path) -> bool:
    """Add the Bitcoin attestation to a pending proof once the calendars have it (hours later)."""
    try:
        from opentimestamps.calendar import RemoteCalendar
        from opentimestamps.core.notary import PendingAttestation
        from opentimestamps.core.serialize import StreamDeserializationContext, StreamSerializationContext
        from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp
    except ImportError:
        return False
    with proof.open("rb") as fh:
        detached = DetachedTimestampFile.deserialize(StreamDeserializationContext(fh))

    def walk(ts: Timestamp) -> bool:
        changed = False
        for att in list(ts.attestations):
            # Only ask calendars we trust; the URI comes from the proof file.
            if isinstance(att, PendingAttestation) and att.uri in CALENDARS:
                try:
                    ts.merge(RemoteCalendar(att.uri).get_timestamp(ts.msg, timeout=30))
                    changed = True
                except Exception:  # not confirmed yet, or calendar unreachable
                    continue
        for sub in list(ts.ops.values()):
            changed |= walk(sub)
        return changed

    if not walk(detached.timestamp):
        return False
    with proof.open("wb") as out:
        detached.serialize(StreamSerializationContext(out))
    return True
