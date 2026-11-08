"""Download the ABN Bulk Extract from data.gov.au and build a local index from it.

Shared by the CLI (`abr-mcp update-index`) and the MCP `build_index` tool. The index is optional:
without one, abr-mcp validates identifiers offline and looks records up through the live ABN Lookup
web services (with an ABR_GUID).
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from .index import BuildReport, IndexScope, LocalIndex, build_index, default_index_path

CKAN_PACKAGE = "https://data.gov.au/data/api/3/action/package_show?id=abn-bulk-extract"
DOWNLOAD_BYTES_ESTIMATE = 1_000_000_000  # the 20 zips, used when data.gov.au does not list sizes


def client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60.0, read=300.0),
                        headers={"User-Agent": "abr-mcp"}, follow_redirects=True)


def zip_resources(c: httpx.Client) -> list[dict[str, Any]]:
    """The bulk extract zips as currently listed by data.gov.au."""
    pkg = c.get(CKAN_PACKAGE)
    pkg.raise_for_status()
    zips = [r for r in pkg.json()["result"]["resources"]
            if str(r.get("url", "")).lower().endswith(".zip")]
    if not zips:
        raise RuntimeError("data.gov.au lists no .zip resources for abn-bulk-extract")
    return zips


def download_bytes(resources: list[dict[str, Any]]) -> int:
    sizes = [int(r["size"]) for r in resources if str(r.get("size") or "").isdigit()]
    return sum(sizes) if len(sizes) == len(resources) else DOWNLOAD_BYTES_ESTIMATE


def stamp(resources: list[dict[str, Any]]) -> str:
    """Identifies a published extract: zip names + their last-modified times."""
    return ";".join(sorted(
        f"{r['url'].rsplit('/', 1)[-1]}={r.get('last_modified') or r.get('size') or ''}"
        for r in resources))


def fetch(c: httpx.Client, resources: list[dict[str, Any]], dest: Path,
          progress: Callable[[str], None] = lambda _m: None) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for i, res in enumerate(resources, 1):
        url = res["url"]
        out = dest / url.rsplit("/", 1)[-1]
        part = out.with_suffix(out.suffix + ".part")
        progress(f"downloading {i}/{len(resources)}: {url}")
        written = 0
        with c.stream("GET", url) as resp:
            resp.raise_for_status()
            expected = int(resp.headers.get("content-length") or 0)
            with open(part, "wb") as fh:
                for chunk in resp.iter_bytes(1 << 20):
                    fh.write(chunk)
                    written += len(chunk)
        if expected and written != expected:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"incomplete download of {out.name} ({written} of {expected} bytes)")
        part.replace(out)
        progress(f"  {written / 1e6:,.0f} MB")


def current_meta(target: Path) -> dict[str, str]:
    idx = LocalIndex(target)
    if not idx.available():
        return {}
    try:
        return idx.meta()
    except Exception:  # unreadable or old format: treat as absent and rebuild
        return {}


def free_bytes(target: Path) -> int:
    p = target.parent
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def update(db: Path | None = None, *, force: bool = False, fts: bool = True, scope: IndexScope | None = None,
           progress: Callable[[str], None] = lambda _m: None,
           client_factory: Callable[[], httpx.Client] = client) -> BuildReport | None:
    """Download the latest extract and build the index. Returns None when the index is already current
    (same published extract, same scope, complete)."""
    target = db or default_index_path()
    scope = scope or IndexScope()
    current = current_meta(target)
    with client_factory() as c:
        resources = zip_resources(c)
        st = stamp(resources)
        if (not force and current.get("source_stamp") == st and current.get("complete") == "1"
                and current.get("scope", "") == scope.to_meta() and current.get("fts") == ("1" if fts else "0")):
            progress(f"index at {target} is current (extract {current.get('extract_dates')}); nothing to do")
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        # Download beside the index (same disk, ~1 GB) and remove afterwards.
        with tempfile.TemporaryDirectory(prefix="abr-download-", dir=target.parent) as tmp:
            fetch(c, resources, Path(tmp), progress)
            return build_index([tmp], target, fts=fts, progress=progress, scope=scope,
                               extra_meta={"source_stamp": st})
