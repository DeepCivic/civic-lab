"""abr-mcp: serve the ABR MCP server, and build or refresh its local index.

  abr-mcp                     serve over stdio (what MCP clients launch)
  abr-mcp serve --http        serve streamable-HTTP on HOST:PORT/mcp
  abr-mcp update-index        download the latest bulk extract and (re)build the
                              index; does nothing if the index is already current
  abr-mcp status              backend status as JSON
  abr-mcp download DIR        just download the extract zips
  abr-mcp build-index PATH... build from zips/XML you already have
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx

from .index import BuildError, BuildReport, LocalIndex, build_index, default_index_path
from .service import AbrService

CKAN_PACKAGE = "https://data.gov.au/data/api/3/action/package_show?id=abn-bulk-extract"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60.0, read=300.0),
                        headers={"User-Agent": "abr-mcp"}, follow_redirects=True)


def _zip_resources(client: httpx.Client) -> list[dict[str, Any]]:
    """The bulk extract zips as currently listed by data.gov.au."""
    pkg = client.get(CKAN_PACKAGE)
    pkg.raise_for_status()
    zips = [r for r in pkg.json()["result"]["resources"]
            if str(r.get("url", "")).lower().endswith(".zip")]
    if not zips:
        raise RuntimeError("data.gov.au lists no .zip resources for abn-bulk-extract")
    return zips


def _stamp(resources: list[dict[str, Any]]) -> str:
    """Identifies a published extract: zip names + their last-modified times."""
    return ";".join(sorted(
        f"{r['url'].rsplit('/', 1)[-1]}={r.get('last_modified') or r.get('size') or ''}"
        for r in resources))


def _fetch(client: httpx.Client, resources: list[dict[str, Any]], dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for res in resources:
        url = res["url"]
        out = dest / url.rsplit("/", 1)[-1]
        part = out.with_suffix(out.suffix + ".part")
        _log(f"downloading {url}")
        written = 0
        with client.stream("GET", url) as resp:
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
        _log(f"  {written / 1e6:,.0f} MB")


def _report_json(rep: BuildReport) -> str:
    return json.dumps({
        "db": str(rep.db_path), "records": rep.record_count, "names": rep.name_count,
        "duplicates_resolved": rep.duplicates_resolved, "complete": rep.complete,
        "extract_dates": rep.extract_dates, "missing_sequence_numbers": rep.missing_sequence_numbers,
        "warnings": rep.warnings, "seconds": rep.seconds,
        "sources": [{"label": s.label, "status": s.status, "records": s.records_parsed,
                     **({"error": s.error} if s.error else {})} for s in rep.sources],
    }, indent=2)


def update_index(db: Path | None, *, force: bool = False, fts: bool = True) -> int:
    target = db or default_index_path()
    idx = LocalIndex(target)
    current: dict[str, str] = {}
    if idx.available():
        try:
            current = idx.meta()
        except Exception as exc:  # unreadable/old format: rebuild
            _log(f"existing index unusable ({exc}); rebuilding")
    with _client() as client:
        resources = _zip_resources(client)
        stamp = _stamp(resources)
        if not force and current.get("source_stamp") == stamp and current.get("complete") == "1":
            _log(f"index at {target} is current (extract {current.get('extract_dates')}); nothing to do")
            return 0
        target.parent.mkdir(parents=True, exist_ok=True)
        # Download beside the index (same disk, ~1 GB) and remove afterwards.
        with tempfile.TemporaryDirectory(prefix="abr-download-", dir=target.parent) as tmp:
            _fetch(client, resources, Path(tmp))
            rep = build_index([tmp], target, fts=fts, progress=_log,
                              extra_meta={"source_stamp": stamp})
    print(_report_json(rep))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="abr-mcp", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    db_help = f"index path (default: $ABR_INDEX_PATH or {default_index_path()})"

    p_serve = sub.add_parser("serve", help="run the MCP server (default)")
    p_serve.add_argument("--http", action="store_true", help="streamable-HTTP on HOST:PORT/mcp")

    p_up = sub.add_parser("update-index", help="download the latest extract and rebuild if changed")
    p_up.add_argument("--db", type=Path, default=None, help=db_help)
    p_up.add_argument("--force", action="store_true", help="rebuild even if already current")
    p_up.add_argument("--no-fts", action="store_true", help="skip the full-text name index")

    p_dl = sub.add_parser("download", help="download the bulk extract zips into a directory")
    p_dl.add_argument("dest", type=Path)

    p_build = sub.add_parser("build-index", help="build the index from zips/XML/directories")
    p_build.add_argument("inputs", nargs="+")
    p_build.add_argument("--db", type=Path, default=None, help=db_help)
    p_build.add_argument("--no-fts", action="store_true", help="skip the full-text name index")
    p_build.add_argument("--allow-partial", action="store_true",
                         help="accept failed or missing files (index is marked partial)")

    sub.add_parser("status", help="show backend status as JSON")

    args = parser.parse_args(argv)
    try:
        if args.cmd in (None, "serve"):
            from . import server
            if getattr(args, "http", False) and "--http" not in sys.argv:
                sys.argv.append("--http")
            server.main()
            return 0
        if args.cmd == "update-index":
            return update_index(args.db, force=args.force, fts=not args.no_fts)
        if args.cmd == "download":
            with _client() as client:
                _fetch(client, _zip_resources(client), args.dest)
            _log(f"done. Next: abr-mcp build-index {args.dest}")
            return 0
        if args.cmd == "build-index":
            rep = build_index(args.inputs, args.db, fts=not args.no_fts,
                              allow_partial=args.allow_partial, progress=_log)
            print(_report_json(rep))
            return 0
        if args.cmd == "status":
            print(json.dumps(AbrService().status(), indent=2))
            return 0
    except BuildError as exc:
        _log(f"build failed, existing index untouched: {exc}")
        return 1
    except (httpx.HTTPError, RuntimeError, OSError) as exc:
        _log(f"error: {exc}")
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
