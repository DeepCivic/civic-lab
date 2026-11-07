"""abr-mcp: serve the ABR MCP server, and optionally build a local index.

The index is optional. Without it, abr-mcp validates ABNs/ACNs offline and looks records up
through the live ABN Lookup web services (set ABR_GUID).

  abr-mcp                     serve over stdio (what MCP clients launch)
  abr-mcp serve --http        serve streamable-HTTP on HOST:PORT/mcp
  abr-mcp estimate [SCOPE]    estimate the size of an index before building it
  abr-mcp update-index [SCOPE] download the latest bulk extract (~1 GB) and (re)build the
                              index; does nothing if the index is already current
  abr-mcp status              backend status as JSON
  abr-mcp download DIR        just download the extract zips
  abr-mcp build-index PATH... [SCOPE]  build from zips/XML you already have

SCOPE keeps part of the register: --active-only, --state VIC (repeatable),
--name-types MN,LGL,BN. The full register is about 7 GB; active ABNs in one state
can be under 1 GB.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from . import updater
from .index import BuildError, BuildReport, IndexScope, build_index, default_index_path, estimate_index
from .service import AbrService

def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _client() -> httpx.Client:
    return updater.client()


def _report_json(rep: BuildReport) -> str:
    return json.dumps({
        "db": str(rep.db_path), "records": rep.record_count, "names": rep.name_count,
        "duplicates_resolved": rep.duplicates_resolved, "complete": rep.complete,
        "records_out_of_scope": rep.records_out_of_scope,
        "extract_dates": rep.extract_dates, "missing_sequence_numbers": rep.missing_sequence_numbers,
        "warnings": rep.warnings, "seconds": rep.seconds,
        "sources": [{"label": s.label, "status": s.status, "records": s.records_parsed,
                     **({"error": s.error} if s.error else {})} for s in rep.sources],
    }, indent=2)


def update_index(db: Path | None, *, force: bool = False, fts: bool = True, scope: IndexScope | None = None) -> int:
    rep = updater.update(db, force=force, fts=fts, scope=scope, progress=_log, client_factory=lambda: _client())
    if rep is not None:
        print(_report_json(rep))
    return 0


def _scope(args: argparse.Namespace) -> IndexScope:
    return IndexScope.make(args.active_only, args.state, args.name_types.split(",") if args.name_types else None)


def _scope_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--active-only", action="store_true", help="keep only active ABNs (about half the size)")
    p.add_argument("--state", action="append", default=None, metavar="STATE",
                   help="keep only records in this state (repeatable), e.g. --state VIC")
    p.add_argument("--name-types", default=None, metavar="TYPES",
                   help="comma-separated name types to keep, e.g. MN,LGL,BN (default: all)")


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
    _scope_args(p_up)

    p_dl = sub.add_parser("download", help="download the bulk extract zips into a directory")
    p_dl.add_argument("dest", type=Path)

    p_build = sub.add_parser("build-index", help="build the index from zips/XML/directories")
    p_build.add_argument("inputs", nargs="+")
    p_build.add_argument("--db", type=Path, default=None, help=db_help)
    p_build.add_argument("--no-fts", action="store_true", help="skip the full-text name index")
    p_build.add_argument("--allow-partial", action="store_true",
                         help="accept failed or missing files (index is marked partial)")
    _scope_args(p_build)

    p_est = sub.add_parser("estimate", help="estimate the size of an index before building it")
    p_est.add_argument("--no-fts", action="store_true")
    _scope_args(p_est)

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
            return update_index(args.db, force=args.force, fts=not args.no_fts, scope=_scope(args))
        if args.cmd == "estimate":
            sc = _scope(args)
            est = estimate_index(sc, fts=not args.no_fts)
            print(json.dumps({"scope": sc.describe(), **est, "gb": round(est["bytes"] / 1e9, 1),
                              "download_gb": round(updater.DOWNLOAD_BYTES_ESTIMATE / 1e9, 1)}, indent=2))
            return 0
        if args.cmd == "download":
            with _client() as client:
                updater.fetch(client, updater.zip_resources(client), args.dest, _log)
            _log(f"done. Next: abr-mcp build-index {args.dest}")
            return 0
        if args.cmd == "build-index":
            rep = build_index(args.inputs, args.db, fts=not args.no_fts,
                              allow_partial=args.allow_partial, progress=_log, scope=_scope(args))
            print(_report_json(rep))
            return 0
        if args.cmd == "status":
            print(json.dumps(AbrService().status(), indent=2))
            return 0
    except BuildError as exc:
        _log(f"build failed, existing index untouched: {exc}")
        return 1
    except (httpx.HTTPError, RuntimeError, OSError, ValueError) as exc:
        _log(f"error: {exc}")
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
