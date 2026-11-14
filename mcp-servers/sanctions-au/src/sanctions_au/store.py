"""Versioned, immutable snapshots of the two source datasets, and the pointer to the current one.

Layout under the data directory:

    snapshots/<source>/<UTC time>-<sha256[:10]>/
        source.<ext>     the file exactly as received
        records.jsonl    the parsed records, one per line
        meta.json        what it came from, when, and the hashes of both files
    current/<source>.json    which snapshot is current, and when it was last confirmed

A snapshot directory is written whole under a temporary name, then renamed into place, and its
files are made read-only. Nothing in it is edited afterwards. The pointer is the only file that
changes, and it is replaced atomically, only after the new snapshot has been parsed and checked.
A failed refresh therefore leaves the previous dataset exactly as it was.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PARSER_VERSION = 1
# A new snapshot with far fewer records than the current one is more likely a broken download
# than a real change, so it is refused unless the person refreshing says otherwise.
MIN_RETAINED_FRACTION = 0.5
SOURCES = ("dfat", "abf")


class DatasetError(ValueError):
    """A dataset is missing, unreadable, or failed a check. The message says what to do."""


def data_dir() -> Path:
    env = os.getenv("SANCTIONS_DATA_DIR")
    if env:
        return Path(env).expanduser()
    if os.name == "nt":
        return Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "sanctions-au"
    return Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "sanctions-au"


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class Dataset:
    source: str
    version: str  # "<source>:<snapshot id>", the value quoted in every screening result
    meta: dict[str, Any]
    checked_at: dt.datetime  # when this snapshot was last confirmed to match the published source
    records: list[dict[str, Any]]


@dataclass(frozen=True)
class CommitResult:
    outcome: str  # "new" | "unchanged"
    version: str
    record_count: int
    previous_record_count: int | None


def pointer(root: Path, source: str) -> dict[str, Any] | None:
    p = root / "current" / f"{source}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DatasetError(f"{p} is unreadable ({exc}); refresh the {source} dataset") from exc


def load(source: str, root: Path | None = None) -> Dataset | None:
    """The current dataset for a source, or None if it was never refreshed. The records file is
    checked against the hash recorded when it was written, so a damaged snapshot is reported
    instead of being screened against."""
    root = root or data_dir()
    ptr = pointer(root, source)
    if ptr is None:
        return None
    snap = root / "snapshots" / source / ptr["snapshot_id"]
    try:
        meta = json.loads((snap / "meta.json").read_text(encoding="utf-8"))
        records_path = snap / "records.jsonl"
        if _sha256(records_path) != meta["records_sha256"]:
            raise DatasetError(f"{source} snapshot {ptr['snapshot_id']} fails its integrity check; "
                               f"run `sanctions-au refresh --source {source}`")
        records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
        checked = dt.datetime.fromisoformat(ptr["checked_at"])
    except (OSError, ValueError, KeyError) as exc:
        if isinstance(exc, DatasetError):
            raise
        raise DatasetError(f"{source} snapshot {ptr['snapshot_id']} is unreadable ({exc!r}); "
                           f"run `sanctions-au refresh --source {source}`") from exc
    return Dataset(source, f"{source}:{ptr['snapshot_id']}", meta, checked, records)


def commit(source: str, raw_file: Path, records: list[dict[str, Any]], extra_meta: dict[str, Any],
           *, root: Path | None = None, force: bool = False, at: dt.datetime | None = None) -> CommitResult:
    """Store a parsed snapshot and make it current. Raises DatasetError, changing nothing, if it
    looks wrong. Identical content to the current snapshot only refreshes the confirmation time."""
    root, at = root or data_dir(), at or now()
    if not records:
        raise DatasetError(f"the new {source} data holds no records; the existing dataset was kept")
    digest = _sha256(raw_file)
    ptr = pointer(root, source)
    previous: dict[str, Any] | None = None
    intact = False
    if ptr:
        snap = root / "snapshots" / source / ptr["snapshot_id"]
        try:
            previous = json.loads((snap / "meta.json").read_text("utf-8"))
            intact = _sha256(snap / "records.jsonl") == previous["records_sha256"]
        except (OSError, ValueError, KeyError, TypeError):
            previous = None  # a damaged current snapshot must not block its own replacement
    prev_count = previous.get("record_count") if previous else None

    # Identical source and an intact snapshot: only the confirmation time changes. A damaged
    # snapshot is never confirmed; the same source is written again as a new snapshot.
    if previous and intact and previous.get("source_sha256") == digest:
        _write_atomic(root / "current" / f"{source}.json",
                      json.dumps({"snapshot_id": ptr["snapshot_id"], "checked_at": at.isoformat()}))
        return CommitResult("unchanged", f"{source}:{ptr['snapshot_id']}", len(records), prev_count)

    if prev_count and not force and len(records) < prev_count * MIN_RETAINED_FRACTION:
        raise DatasetError(f"the new {source} data has {len(records)} records against {prev_count} in the current "
                           "dataset. That is more likely a broken download than a real change, so the current "
                           "dataset was kept. Re-run with --force if the drop is real.")

    snapshot_id = f"{at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:10]}"
    n = 1
    while (root / "snapshots" / source / snapshot_id).exists():  # e.g. repairing a snapshot written this second
        n += 1
        snapshot_id = f"{at.strftime('%Y%m%dT%H%M%SZ')}-{digest[:10]}-{n}"
    final = root / "snapshots" / source / snapshot_id
    final.parent.mkdir(parents=True, exist_ok=True)
    building = Path(tempfile.mkdtemp(dir=final.parent, prefix=".building-"))
    try:
        shutil.copyfile(raw_file, building / f"source{raw_file.suffix}")
        (building / "records.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records), encoding="utf-8")
        meta = {"source": source, "snapshot_id": snapshot_id, "dataset_version": f"{source}:{snapshot_id}",
                "source_file": f"source{raw_file.suffix}", "source_sha256": digest,
                "records_sha256": _sha256(building / "records.jsonl"), "record_count": len(records),
                "retrieved_at": at.isoformat(), "parser_version": PARSER_VERSION, **extra_meta}
        (building / "meta.json").write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
        for f in building.iterdir():
            f.chmod(0o444)
        building.rename(final)
    except BaseException:
        for f in building.glob("*"):
            f.chmod(0o644)
        shutil.rmtree(building, ignore_errors=True)
        raise
    _write_atomic(root / "current" / f"{source}.json",
                  json.dumps({"snapshot_id": snapshot_id, "checked_at": at.isoformat()}))
    return CommitResult("new", f"{source}:{snapshot_id}", len(records), prev_count)
