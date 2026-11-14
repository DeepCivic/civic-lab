"""sanctions-au: serve the MCP server, and refresh the data it screens against.

  sanctions-au                      serve over stdio (what MCP clients launch)
  sanctions-au serve --http         serve streamable-HTTP on HOST:PORT/mcp
  sanctions-au refresh              fetch both sources and store them as new versioned snapshots
  sanctions-au refresh --source dfat --dfat-file FILE    import a file you downloaded yourself
  sanctions-au status               installed datasets as JSON

Refreshing is the only thing that uses the network, and it is a separate command on purpose, so
the server can run where there is none. A refresh that fails any check leaves the current
dataset untouched.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx

from . import abf, dfat, store

MAX_DFAT_BYTES = 50_000_000


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(30.0, read=120.0), headers={"User-Agent": abf.USER_AGENT},
                        follow_redirects=True)


def _download(client: httpx.Client, url: str, dest: Path, limit: int) -> None:
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        size = 0
        with dest.open("wb") as f:
            for chunk in resp.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise store.DatasetError(f"{url} is larger than {limit} bytes; refusing it")
                f.write(chunk)


def refresh_source(source: str, local: Path | None, force: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="sanctions-au-") as tmp:
        if source == "dfat":
            raw = Path(tmp) / "source.xlsx"
            if local:
                raw.write_bytes(local.read_bytes())
            else:
                with _client() as c:
                    _download(c, dfat.SOURCE_URL, raw, MAX_DFAT_BYTES)
            records, facts = dfat.parse(raw)
            meta = {"source_url": dfat.SOURCE_URL if not local else None, "origin": "file" if local else "download",
                    "list_date": facts["list_date"], "sheet_name": facts["sheet_name"], "name_rows": facts["name_rows"]}
        else:
            raw = Path(tmp) / "source.json"
            if local:
                raw.write_bytes(local.read_bytes())
            else:
                with _client() as c:
                    raw.write_bytes(abf.fetch(c))
            records = abf.parse(raw.read_bytes())
            meta = {"source_url": abf.ENDPOINT_URL if not local else None, "origin": "file" if local else "download",
                    "page_url": abf.PAGE_URL}
        res = store.commit(source, raw, records, meta, force=force)
    return {"outcome": res.outcome, "dataset_version": res.version, "records": res.record_count,
            "previous_records": res.previous_record_count}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sanctions-au", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd")
    p_serve = sub.add_parser("serve", help="run the MCP server (default)")
    p_serve.add_argument("--http", action="store_true", help="streamable-HTTP on HOST:PORT/mcp")
    p_ref = sub.add_parser("refresh", help="fetch the sources and store new versioned snapshots")
    p_ref.add_argument("--source", choices=["all", *store.SOURCES], default="all")
    p_ref.add_argument("--dfat-file", type=Path, help="import this DFAT .xlsx instead of downloading it")
    p_ref.add_argument("--abf-file", type=Path, help="import this saved ABF response (JSON) instead of downloading it")
    p_ref.add_argument("--force", action="store_true", help="accept a snapshot with far fewer records than the current one")
    sub.add_parser("status", help="show installed datasets as JSON")

    args = parser.parse_args(argv)
    if args.cmd in (None, "serve"):
        from . import server
        if getattr(args, "http", False) and "--http" not in sys.argv:
            sys.argv.append("--http")
        server.main()
        return 0
    if args.cmd == "status":
        from .service import Screener
        print(json.dumps(Screener().status(), indent=2))
        return 0

    failed, report = False, {}
    for source in (store.SOURCES if args.source == "all" else (args.source,)):
        local = args.dfat_file if source == "dfat" else args.abf_file
        try:
            report[source] = refresh_source(source, local, args.force)
        except (store.DatasetError, httpx.HTTPError, OSError) as exc:
            failed = True
            hint = (" If the site refuses automated downloads, save the file in a browser and use "
                    "--dfat-file." if source == "dfat" and not local else "")
            report[source] = {"outcome": "failed", "error": f"{exc}{hint}", "kept": "the previous dataset, unchanged"}
    print(json.dumps(report, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
