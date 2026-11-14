"""Sanctions MCP server: screening against Australian sanctions data, offline.

Run with:  python -m sanctions_au.server          (stdio)
           python -m sanctions_au.server --http   (streamable-HTTP, stateless, /mcp)
"""

from __future__ import annotations

import functools
import os
import sys
from collections.abc import Callable
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

from . import gleif_tools, store
from .service import MAX_BATCH, Screener, Subject, SubjectType

INSTRUCTIONS = """\
Screens people, organisations, vessels and sponsors against two Australian sources, using locally
held snapshots: the DFAT Consolidated List (sanctions designations) and the ABF Register of
Sanctioned Sponsors. Unofficial: not affiliated with or endorsed by DFAT, the ABF or the Commonwealth.
Screening makes no network call, and nothing about a subject leaves this machine.

- Results are potential matches, never legal conclusions. Do not tell the user a subject IS sanctioned,
  or is clear. Present each match with why it was returned (matched_on), what disagrees (conflicts),
  and its confidence. Confidence is a rule-based summary of how many checks agree, not a probability.
- Read `status` per source: potential_match, no_match, insufficient_information (say what to add),
  not_applicable, or dataset_unavailable. 'overall' is 'incomplete' when any source could not be
  screened in full, so never present it as a clear result.
- Always report dataset_versions and any warnings (stale data, the ABF's monthly update lag, pending
  review). A 'no match' on stale data is weak: say so.
- Supply as much as you have: name, aliases, date of birth (year compared), country, address, passport
  or other identifier, IMO (vessels), ABN/ACN (sponsors). More detail separates real matches from
  coincidences. A name alone never reaches 'high'.
- screen_batch screens up to 100 subjects in one call. get_record returns the full record for a match.
- The data is refreshed outside the server with `sanctions-au refresh`; dataset_status says how old it is.

Separately, twelve GLEIF tools look up Legal Entity Identifiers (lei_lookup, validate_lei, batch_lei_lookup,
search_entity, search_by_bic, search_by_isin, search_by_country, get_relationships, autocomplete, get_lei_issuer,
list_lei_issuers, get_reporting_exceptions). Unlike screening, they send what you ask about to api.gleif.org, so
they are off unless the operator sets SANCTIONS_ENABLE_GLEIF=1; if one reports 'disabled', tell the user, do not
retry. An LEI match is identity information, not a sanctions result. An entity having no parent is normal and is
explained by get_reporting_exceptions.
"""

mcp = _Server("sanctions", instructions=INSTRUCTIONS)
_screener: Screener | None = None
F = TypeVar("F", bound=Callable[..., Any])


def screener() -> Screener:
    global _screener
    if _screener is None:
        _screener = Screener()
    return _screener


def anticipated(fn: F) -> F:
    """Report expected failures (bad input, a missing or damaged dataset) with their message.
    MCP SDKs hide the text of any other exception."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:  # includes store.DatasetError
            raise ToolError(str(exc)) from exc

    return wrapper  # type: ignore[return-value]


Sources = Literal["all", "dfat", "abf"]
SOURCES_HELP = "all (default), dfat (Consolidated List only) or abf (Register of Sanctioned Sponsors only)."


@mcp.tool()
@anticipated
def screen_subject(
    name: Annotated[str | None, Field(description="Person, organisation, vessel or sponsor name.")] = None,
    aliases: Annotated[list[str] | None, Field(description="Other names to screen as well.")] = None,
    subject_type: Annotated[SubjectType, Field(description="individual, organisation, vessel, sponsor or any. "
                                                           "Narrows DFAT; vessels are not screened against the ABF.")] = "any",
    date_of_birth: Annotated[str | None, Field(description="Year or full date. Only the year is compared.")] = None,
    country: Annotated[str | None, Field(description="Nationality or country, as a country name.")] = None,
    address: Annotated[str | None, Field(description="Address or place; matched on shared words.")] = None,
    identifier: Annotated[str | None, Field(description="Passport or other identifier number.")] = None,
    imo: Annotated[str | None, Field(description="Vessel IMO number.")] = None,
    abn: Annotated[str | None, Field(description="ABN, for sponsors.")] = None,
    acn: Annotated[str | None, Field(description="ACN, for sponsors.")] = None,
    sanctioned_from: Annotated[str | None, Field(description="ABF only: earliest sanction date, YYYY-MM-DD.")] = None,
    sanctioned_to: Annotated[str | None, Field(description="ABF only: latest sanction date, YYYY-MM-DD.")] = None,
    sources: Annotated[Sources, Field(description=SOURCES_HELP)] = "all",
) -> dict[str, Any]:
    """Screen one subject against the DFAT Consolidated List and/or the ABF Register of Sanctioned Sponsors.

    Returns, per source, a status (potential_match, no_match, insufficient_information, not_applicable or
    dataset_unavailable) and any potential matches, each with why it matched, what conflicts, a confidence
    level and the record. Also returns the dataset versions used, warnings and a disclaimer. These are
    potential matches for human review, never a legal conclusion.
    """
    subject = Subject(name=name, aliases=aliases or [], subject_type=subject_type, date_of_birth=date_of_birth,
                      country=country, address=address, identifier=identifier, imo=imo, abn=abn, acn=acn,
                      sanctioned_from=sanctioned_from, sanctioned_to=sanctioned_to)
    s = screener()
    now = store.now()
    return {**s.screen(subject, sources, now), **s.envelope(sources, now)}


@mcp.tool()
@anticipated
def screen_batch(
    subjects: Annotated[list[Subject], Field(description=f"1 to {MAX_BATCH} subjects. Give each a `ref` of your own "
                                                         "to join results back to your list.", min_length=1,
                                             max_length=MAX_BATCH)],
    sources: Annotated[Sources, Field(description=SOURCES_HELP)] = "all",
) -> dict[str, Any]:
    """Screen up to 100 subjects in one call, for onboarding, supplier review or periodic rescreening.

    Results come back in input order with a summary count per overall status. Dataset versions, warnings
    and the disclaimer appear once for the whole batch.
    """
    return screener().screen_many(subjects, sources)


@mcp.tool()
@anticipated
def get_record(
    source: Annotated[Literal["dfat", "abf"], Field(description="Which dataset the record is in.")],
    record_id: Annotated[str, Field(description="record_id from a screening result.")],
) -> dict[str, Any]:
    """Get the full stored record for a match, including every alias for a DFAT listing.

    Record ids belong to one dataset version. After a refresh, screen again for current ids.
    """
    return screener().record(source, record_id)


@mcp.tool()
@anticipated
def dataset_status() -> dict[str, Any]:
    """Which datasets are installed: version, record count, when each was last confirmed against the
    published source, its age, whether it is stale, and the SHA-256 of the source file it came from."""
    return screener().status()


gleif_tools.register(mcp, anticipated)


def main() -> None:
    """Serve over stdio, or streamable-HTTP (stateless, /mcp) with --http or MCP_TRANSPORT=http
    on HOST (default 127.0.0.1) and PORT (default 8000)."""
    http = "--http" in sys.argv or os.getenv("MCP_TRANSPORT", "").lower() in ("http", "streamable-http")
    if not http:
        mcp.run()
        return
    host, port = os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "8000"))
    if _MCP_V2:
        mcp.run("streamable-http", host=host, port=port, stateless_http=True)
    else:
        mcp.settings.host, mcp.settings.port = host, port
        mcp.settings.stateless_http = True
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
