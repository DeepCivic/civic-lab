"""ABR MCP server: Australian Business Register (ABN Lookup) data over MCP.

Run with:  python -m abr_au.server          (stdio)
           python -m abr_au.server --http   (streamable-HTTP, stateless, /mcp)
"""

from __future__ import annotations

import functools
import os
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

from pydantic import Field

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError

    _MCP_V2 = True
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

    _MCP_V2 = False

from abr_au import jobs as _jobs
from abr_au.identifiers import validate_abn as _validate_abn
from abr_au.identifiers import validate_acn as _validate_acn
from abr_au.index import IndexScope, IndexUnavailable
from abr_au.service import AbrService
from abr_au.web import WebError

INSTRUCTIONS = """\
Australian Business Register (ABN Lookup) data, via an unofficial client that
is not affiliated with or endorsed by the ABR or the Commonwealth. Do not
present results as official ABR statements.

- Validate before you look up: validate_abn / validate_acn are offline checksum
  checks. An ABN failing its checksum cannot be registered.
- Join on ABN, not name. Exact ABN lookups are deterministic; name search
  returns *candidates* that must be confirmed by ABN.
- Every response carries `provenance`. Bulk-extract data is a weekly snapshot
  (see extract_date); web-service data is live.
- ABR data does not reveal ownership, control or parent companies, and
  state/postcode is the main business location only.
- Trading names (TRD) are legacy (not updated since 2012) and the ABR
  recommends avoiding them; search_names skips them unless asked. Registered
  business names (BN) are current.
- Backends: lookups use the live ABN Lookup web services when ABR_GUID is set,
  and/or a local index of the weekly bulk extract. The index is optional. Only
  offer build_index if the user wants offline or bulk lookups: it downloads
  about 1 GB, and can be scoped (active ABNs, chosen states) to stay small.
  Call it without start first, show the user the plan, and start only if they agree.
"""

mcp = _Server("abr", instructions=INSTRUCTIONS)
_service: AbrService | None = None
_builds = _jobs.Builds()
_HTTP = False


def service() -> AbrService:
    global _service
    if _service is None:
        _service = AbrService()
    return _service


F = TypeVar("F", bound=Callable[..., Any])


def anticipated(fn: F) -> F:
    """Report expected failures (bad input, no backend, web/index errors) to the
    client with their message. MCP SDKs hide the text of any other exception."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (ValueError, IndexUnavailable, WebError) as exc:
            raise ToolError(str(exc)) from exc
        except sqlite3.DatabaseError as exc:
            raise ToolError(f"local ABR index error ({exc}); rebuild it with the build_index tool "
                            "or `abr-au update-index`") from exc

    return wrapper  # type: ignore[return-value]


Source = Literal["auto", "local", "web"]
SOURCE_HELP = (
    "auto: local bulk-extract index, falling back to the live web service on a miss "
    "(if ABR_GUID is set); local: offline index only; web: live ABN Lookup only."
)


@mcp.tool()
@anticipated
def validate_abn(
    abn: Annotated[str, Field(description="ABN in any format, e.g. '51 824 753 556' or 'ABN: 51-824-753-556'.")],
) -> dict[str, Any]:
    """Check an ABN's format and checksum offline (no lookup).

    Normalises spacing, punctuation and spreadsheet float damage (e.g.
    '51824753556.0'), then applies the ATO check-digit rule. Returns the
    11-digit key to join on, a display format, and a reason when invalid
    (too_few_digits, too_many_digits, checksum_failed, ...). Notes flag likely
    mix-ups such as an ACN passed as an ABN.
    """
    return _validate_abn(abn)


@mcp.tool()
@anticipated
def validate_acn(
    acn: Annotated[str, Field(description="ACN or ARBN in any format, e.g. '004 085 616'.")],
) -> dict[str, Any]:
    """Check an ACN/ARBN's format and checksum offline (no lookup).

    If digits look lost to a spreadsheet (fewer than 9), the zero-padded
    candidate is reported, never silently assumed. An ABN passed by mistake is
    noted, with the ACN it embeds when it has one.
    """
    return _validate_acn(acn)


@mcp.tool()
@anticipated
def lookup_abn(
    abn: Annotated[str, Field(description="ABN in any format.")],
    source: Annotated[Source, Field(description=SOURCE_HELP)] = "auto",
) -> dict[str, Any]:
    """Get the ABR record for one ABN.

    Returns status (ACT/CAN) and date, entity name and type, ACN, GST
    registration, DGR endorsement, registered business names, legacy trading
    names, and main business state/postcode, with provenance. An invalid ABN
    is reported as such without a lookup. A miss on the local index says
    whether the index is complete and as at what date.
    """
    return service().lookup_abn(abn, source)


@mcp.tool()
@anticipated
def lookup_abns(
    abns: Annotated[list[str], Field(description="ABNs in any format (up to 1000 local, 25 web).")],
    source: Annotated[Source, Field(description="local (default) or web; auto picks local if built.")] = "local",
) -> dict[str, Any]:
    """Validate and look up many ABNs at once, for joining a dataset to the ABR.

    One compact row per input (in input order): validity, found, entity name,
    status, entity type, state, postcode, ACN, GST. Use this rather than many
    lookup_abn calls when reconciling a list (suppliers, grant recipients).
    """
    return service().lookup_abns(abns, source)


@mcp.tool()
@anticipated
def lookup_acn(
    acn: Annotated[str, Field(description="ACN in any format.")],
    source: Annotated[Source, Field(description=SOURCE_HELP)] = "auto",
) -> dict[str, Any]:
    """Find the ABN record(s) for a company's ACN (ASIC number)."""
    return service().lookup_acn(acn, source)


@mcp.tool()
@anticipated
def search_names(
    name: Annotated[str, Field(description="Entity, business or trading name to search for.")],
    mode: Annotated[
        Literal["auto", "exact", "tokens"],
        Field(description="exact: same normalised name (legal-form words like PTY LTD and a leading "
                          "'THE' ignored); tokens: all words present as prefixes; auto: exact first, "
                          "then tokens."),
    ] = "auto",
    state: Annotated[str | None, Field(description="Filter by main business state, e.g. 'NSW'.")] = None,
    postcode: Annotated[str | None, Field(description="Filter by main business postcode.")] = None,
    active_only: Annotated[bool, Field(description="Only ABNs with status ACT.")] = False,
    name_types: Annotated[
        list[str] | None,
        Field(description="Name types to search: MN, LGL, BN, OTN, DGR (default), or include TRD "
                          "for legacy trading names, which the ABR recommends avoiding."),
    ] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    source: Annotated[Source, Field(description=SOURCE_HELP)] = "auto",
) -> dict[str, Any]:
    """Search ABR names and return candidate ABNs, one result per ABN.

    Each result says how it matched (exact_name / all_tokens) and which names
    matched. Results are candidates, not identity: confirm with lookup_abn
    before relying on one.
    """
    return service().search_names(name, mode=mode, state=state, postcode=postcode,
                                  active_only=active_only, name_types=name_types,
                                  limit=limit, source=source)


@mcp.tool()
@anticipated
def register_status() -> dict[str, Any]:
    """Report which ABR backends are available, the extract date and age,
    completeness, the local index's scope and record counts, the progress of
    any index build, and the data licence/attribution."""
    out = service().status()
    job = _builds.status()
    if job:
        out["index_build"] = job
    out["index_build_allowed"] = _jobs.allowed(_HTTP)
    return out


@mcp.tool()
@anticipated
def build_index(
    start: Annotated[bool, Field(description="false: return the plan (download, estimated size, free disk). "
                                             "true: start the build in the background")] = False,
    active_only: Annotated[bool, Field(description="Keep only active ABNs (about 45% of records)")] = False,
    states: Annotated[list[str] | None, Field(description="Keep only these states, e.g. ['VIC']. Default: all")] = None,
    name_types: Annotated[list[str] | None, Field(description="Name types to keep (MN, LGL, BN, TRD, OTN, DGR). "
                                                              "Default: all. Dropping TRD (legacy) saves space")] = None,
    name_search: Annotated[bool, Field(description="Build the full-text name index for word and prefix "
                                                   "search (about 10% more space)")] = True,
    source_dir: Annotated[str | None, Field(description="Build from bulk extract zips or XML already on disk "
                                                        "instead of downloading")] = None,
    force: Annotated[bool, Field(description="Rebuild even if the index is already current")] = False,
) -> dict[str, Any]:
    """Optional: build a local index of the ABN Bulk Extract, for offline lookups, bulk joins, and use
    without an ABR_GUID. Not needed otherwise. Call first without start to get the plan (download about
    1 GB; the full register is about 7 GB, active ABNs in one state can be under 1 GB). Call again with
    start=true to build in the background, and check register_status for progress. The current index,
    if any, keeps working until the new one replaces it."""
    if not _jobs.allowed(_HTTP):
        raise ValueError("Index builds are disabled on this server (HTTP mode needs ABR_ALLOW_INDEX_BUILD=1).")
    scope = IndexScope.make(active_only, states, name_types)
    src = Path(source_dir).expanduser() if source_dir else None
    if src is not None and not src.exists():
        raise ValueError(f"source_dir not found: {src}")
    target = service().index.path
    if not start:
        plan = _builds.plan(scope, fts=name_search, source_dir=src, target=target)
        return {"plan": plan, "next": "Show this plan to the user. If they agree, call build_index again "
                                      "with the same options and start=true."}
    job = _builds.start(scope, fts=name_search, source_dir=src, force=force, target=target)
    return {"started": True, "index_build": job, "next": "Check register_status for progress."}


@mcp.tool()
@anticipated
def explain_codes() -> dict[str, Any]:
    """Code tables: ABN status, GST status, name types, states, and the entity
    type codes present in the local index (with record counts)."""
    return service().codes()


def main() -> None:
    """Serve over stdio, or streamable-HTTP (stateless, /mcp) with --http or
    MCP_TRANSPORT=http on HOST (default 127.0.0.1) and PORT (default 8000)."""
    global _HTTP
    http = "--http" in sys.argv or os.getenv("MCP_TRANSPORT", "").lower() in ("http", "streamable-http")
    _HTTP = http
    if not http:
        mcp.run()
        return
    # Loopback by default: an exposed endpoint lets anyone spend the configured
    # ABR_GUID. Containers and hosts opt in to 0.0.0.0 explicitly.
    host, port = os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "8000"))
    if _MCP_V2:
        mcp.run("streamable-http", host=host, port=port, stateless_http=True)
    else:
        mcp.settings.host, mcp.settings.port = host, port
        mcp.settings.stateless_http = True
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
