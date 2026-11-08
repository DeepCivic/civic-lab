"""Background index builds for the MCP `build_index` tool.

A build downloads about 1 GB and takes minutes, so the tool plans first, then starts the build in a
background thread and returns at once. `register_status` reports progress. One build runs at a time;
the existing index keeps answering until the new one is swapped in (build_index is atomic).
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import updater
from .index import BuildError, IndexScope, build_index, default_index_path, estimate_index

ALLOW_ENV = "ABR_ALLOW_INDEX_BUILD"
_LOG_LINES = 12


def allowed(http: bool) -> bool:
    """Builds are allowed on a local (stdio) server. Over HTTP a remote client could trigger a 1 GB
    download and fill the host's disk, so they need ABR_ALLOW_INDEX_BUILD=1."""
    flag = os.getenv(ALLOW_ENV, "").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False
    return not http or flag in ("1", "true", "yes", "on")


def _gb(n: int) -> float:
    return round(n / 1e9, 1)


class Builds:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._job: dict[str, Any] | None = None
        self._thread: threading.Thread | None = None

    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def status(self) -> dict[str, Any] | None:
        with self._lock:
            return None if self._job is None else {**self._job, "log": list(self._job["log"])}

    def plan(self, scope: IndexScope, *, fts: bool, source_dir: Path | None, target: Path | None = None) -> dict[str, Any]:
        target = target or default_index_path()
        est = estimate_index(scope, fts)
        current = updater.current_meta(target)
        out: dict[str, Any] = {
            "target": str(target),
            "scope": scope.describe(),
            "full_text_name_search": fts,
            "estimated_index_gb": _gb(est["bytes"]),
            "estimated_records": est["records"],
            "estimated_names": est["names"],
            "free_disk_gb": _gb(updater.free_bytes(target)),
            "replaces_existing_index": bool(current),
            "estimate_basis": "Counts from the complete extract of 22 April 2026; the real size varies by a few per cent.",
        }
        if source_dir is None:
            try:
                with updater.client() as c:
                    resources = updater.zip_resources(c)
                out["download_gb"] = _gb(updater.download_bytes(resources))
                out["download_from"] = "data.gov.au (ABN Bulk Extract, 20 zip files, CC BY 3.0 AU)"
                if current.get("source_stamp") == updater.stamp(resources) and current.get("scope", "") == scope.to_meta() \
                        and current.get("complete") == "1":
                    out["already_current"] = "The existing index is from this extract with this scope; pass force=true to rebuild."
            except Exception as exc:  # network down: still give the estimate
                out["download_gb"] = _gb(updater.DOWNLOAD_BYTES_ESTIMATE)
                out["download_listing_error"] = str(exc)
            dl = int(out["download_gb"] * 1e9)
        else:
            out["source_dir"] = str(source_dir)
            dl = 0
        # Room for the download, the new index, and SQLite's sort spill while indexing.
        need = dl + 2 * est["bytes"]
        out["disk_needed_gb"] = _gb(need)
        if updater.free_bytes(target) < need:
            out["warning"] = f"Not enough free disk: about {_gb(need)} GB is needed at {target.parent}."
        out["takes"] = "Roughly 5 to 20 minutes, depending on the connection and disk."
        return out

    def start(self, scope: IndexScope, *, fts: bool, source_dir: Path | None, force: bool,
              target: Path | None = None) -> dict[str, Any]:
        target = target or default_index_path()
        with self._lock:
            if self.running():
                raise ValueError("An index build is already running; check register_status for progress.")
            self._job = {"state": "running", "stage": "starting", "target": str(target), "scope": scope.describe(),
                         "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "log": []}
            self._thread = threading.Thread(target=self._run, args=(scope, fts, source_dir, force, target),
                                            name="abr-index-build", daemon=True)
            self._thread.start()
        return self.status() or {}

    def _progress(self, msg: str) -> None:
        with self._lock:
            if self._job is None:
                return
            stage = msg.strip().split(" ", 1)[0].rstrip(":")
            if stage in ("downloading", "reading", "indexing", "building", "analysing"):
                self._job["stage"] = stage
            self._job["log"] = (self._job["log"] + [msg.strip()])[-_LOG_LINES:]

    def _run(self, scope: IndexScope, fts: bool, source_dir: Path | None, force: bool, target: Path) -> None:
        t0 = time.monotonic()
        try:
            if source_dir is not None:
                rep = build_index([source_dir], target, fts=fts, progress=self._progress, scope=scope)
            else:
                rep = updater.update(target, force=force, fts=fts, scope=scope, progress=self._progress,
                                     client_factory=lambda: updater.client())
            result: dict[str, Any] = {"state": "done", "stage": "done"}
            if rep is None:
                result["result"] = "The index was already current; nothing was rebuilt."
            else:
                result["result"] = {"records": rep.record_count, "names": rep.name_count, "complete": rep.complete,
                                    "extract_dates": rep.extract_dates, "records_out_of_scope": rep.records_out_of_scope,
                                    "size_gb": _gb(target.stat().st_size), "warnings": rep.warnings}
        except (BuildError, OSError, RuntimeError, ValueError, Exception) as exc:  # noqa: BLE001 - report every failure
            result = {"state": "failed", "error": f"{type(exc).__name__}: {exc}",
                      "note": "Any existing index was left in place."}
        with self._lock:
            if self._job is not None:
                self._job.update(result, seconds=round(time.monotonic() - t0, 1),
                                 finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def wait(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
