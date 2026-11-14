"""The twelve GLEIF tools, registered on the sanctions server.

They keep the Go gleif-mcp-server's tool names and output keys, so prompts written for it still
work. Unlike the screening tools they send queries to api.gleif.org, so each one refuses to run
until the operator sets SANCTIONS_ENABLE_GLEIF=1.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Annotated, Any

from pydantic import Field

from .gleif import AUTOCOMPLETE_MAX, MAX_BATCH, Client, GleifError, check_digits_ok

ENV = "SANCTIONS_ENABLE_GLEIF"
LEI = Annotated[str, Field(description="20-character LEI code, e.g. HWUPKR0MPOU8FGXBT394")]  # module level: annotations are resolved here
_client: Client | None = None
TOOLS: dict[str, Callable[..., Any]] = {}  # the registered functions by name, so tests can call them directly


def enabled() -> bool:
    return os.getenv(ENV, "").strip().lower() in ("1", "true", "yes")


def client() -> Client:
    global _client
    if not enabled():
        raise GleifError("disabled", f"GLEIF lookups are off. They send what you ask about to api.gleif.org, unlike "
                                     f"sanctions screening, which never leaves the machine. Set {ENV}=1 to allow them.")
    if _client is None:
        _client = Client()
    return _client


def register(mcp: Any, anticipated: Callable[..., Any]) -> None:
    try:  # tool hints (read-only, talks to an outside service); older SDKs may not take them
        from mcp.types import ToolAnnotations
        hints: dict[str, Any] = {"annotations": ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)}
    except ImportError:
        hints = {}

    def tool(fn: Callable[..., Any]) -> Callable[..., Any]:
        wrapped = anticipated(fn)
        TOOLS[fn.__name__] = wrapped
        return mcp.tool(**hints)(wrapped)

    @tool
    def lei_lookup(lei: LEI) -> dict[str, Any]:
        """Get full details for one LEI (legal name, addresses, jurisdiction, status, managing LOU, renewal dates).
        USE WHEN: "look up LEI", "who is HWUPKR0MPOU8FGXBT394?". For several, use batch_lei_lookup. For format and
        status only, use validate_lei. FAILS WHEN: the LEI is not 20 alphanumeric characters, or is not in GLEIF
        (the entity may have none: try search_entity by name)."""
        return client().get_lei(lei)

    @tool
    def validate_lei(lei: Annotated[str, Field(description="LEI to check, in any format. Reports valid=false instead of erroring.")]) -> dict[str, Any]:
        """Check an LEI's format, ISO 17442 check digits and GLEIF registration status. Never errors for a bad LEI:
        it returns valid=false with the reason, so it is safe on untrusted input. format_valid and registry_checked
        say how far the check got: valid=false with registry_checked=false means GLEIF could not be reached, not
        that the LEI is bad. Format and check digits are checked offline."""
        if not enabled():  # the offline checks need no network, so they stay available when GLEIF is off
            raw = (lei or "").strip().upper()
            ok = len(raw) == 20 and raw.isalnum() and check_digits_ok(raw)
            return {"lei": raw, "valid": False, "format_valid": ok, "registry_checked": False,
                    "message": ("Format and check digits are valid; the registry was not checked because "
                                f"{ENV} is not set." if ok else "Invalid LEI: wrong format or failed ISO 17442 check digits")}
        return client().validate(lei)

    @tool
    def batch_lei_lookup(leis: Annotated[str, Field(description=f"Comma-separated LEI codes (max {MAX_BATCH}).")]) -> dict[str, Any]:
        """Look up several LEIs in one request. Returns requested, found, the records, and notFound.
        FAILS WHEN: the list is empty, has more than 100 LEIs, or any entry has an invalid format."""
        return client().batch(leis.split(","))

    @tool
    def search_entity(
        query: Annotated[str, Field(description="Company name to search.")],
        limit: Annotated[int, Field(description="Results per page, 1-100 (default 20).")] = 20,
        page: Annotated[int, Field(description="Page number from 1.")] = 1,
        fuzzy: Annotated[bool, Field(description="Typo-tolerant full-text match (default true); false matches the legal name.")] = True,
    ) -> dict[str, Any]:
        """Find legal entities by name, with pagination. USE WHEN: "find company X". For name suggestions use autocomplete."""
        return client().search_entity(query, limit, page, fuzzy)

    @tool
    def search_by_bic(bic: Annotated[str, Field(description="BIC/SWIFT code, 8 or 11 characters, e.g. CHASUS33")]) -> dict[str, Any]:
        """Find the LEI for a bank's BIC/SWIFT code. An 8-character BIC is looked up in its 11-character
        primary-office form (XXX) first, because GLEIF stores BICs that way."""
        return client().search_by_bic(bic)

    @tool
    def search_by_isin(isin: Annotated[str, Field(description="12-character ISIN, e.g. US0378331005")]) -> dict[str, Any]:
        """Find the issuer LEI for a security's ISIN."""
        return client().search_by_isin(isin)

    @tool
    def search_by_country(
        country: Annotated[str, Field(description="2-letter ISO 3166-1 alpha-2 code, e.g. AU")],
        limit: Annotated[int, Field(description="Results, 1-100 (default 20). Does not page.")] = 20,
    ) -> dict[str, Any]:
        """Browse entities by legal-address country."""
        return client().search_by_country(country, limit)

    @tool
    def get_relationships(
        lei: LEI,
        type: Annotated[str, Field(description="direct-parent (default), ultimate-parent, children, fund-manager, umbrella-fund, sub-funds")] = "direct-parent",
    ) -> dict[str, Any]:
        """Get corporate ownership relationships: parents, children and fund relationships. FAILS WHEN: none is on
        file. A record with no parent usually files a reporting exception instead: use get_reporting_exceptions."""
        return client().relationships(lei, type)

    @tool
    def autocomplete(
        prefix: Annotated[str, Field(description="Name prefix, at least 2 characters.")],
        limit: Annotated[int, Field(description=f"Suggestions, 1-{AUTOCOMPLETE_MAX} (GLEIF serves at most {AUTOCOMPLETE_MAX}).")] = AUTOCOMPLETE_MAX,
    ) -> dict[str, Any]:
        """Suggest entity names from a prefix."""
        return client().autocomplete(prefix, limit)

    @tool
    def get_lei_issuer(issuer_id: Annotated[str, Field(description="LEI issuer (Local Operating Unit) ID, 4-32 alphanumeric characters.")]) -> dict[str, Any]:
        """Get one LEI issuer (a Local Operating Unit)."""
        return client().issuer(issuer_id)

    @tool
    def list_lei_issuers(limit: Annotated[int, Field(description="Issuers to return, 1-1000 (default 100). Does not page.")] = 100) -> dict[str, Any]:
        """List the LEI issuers (Local Operating Units)."""
        return client().issuers(limit)

    @tool
    def get_reporting_exceptions(lei: LEI) -> dict[str, Any]:
        """Get the reporting exceptions an entity filed for not naming a direct and/or ultimate parent, with the
        category, reason and reference GLEIF holds. FAILS WHEN: none is on file. That has two meanings the server
        cannot tell apart: the LEI does not exist, or it exists and files none (for example because it reports a parent)."""
        return client().reporting_exceptions(lei)
