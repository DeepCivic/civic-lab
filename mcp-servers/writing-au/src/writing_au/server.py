"""Australian Writing MCP server.

Exposes three deterministic content-quality tools over MCP (stdio):
  * check_spelling     - Australian English spelling
  * check_grammar      - rule-based grammar / punctuation / usage
  * get_reading_level  - Australian school year reading level

Run with:  python -m australian_writing.server
"""

from __future__ import annotations

import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .grammar import check_grammar as _check_grammar
from .readability import get_reading_level as _get_reading_level
from .spelling import check_spelling as _check_spelling

mcp = FastMCP("australian-writing")


@mcp.tool()
def check_spelling(text: str) -> dict[str, Any]:
    """Check text against Australian English spelling.

    Flags American spellings (e.g. color -> colour) as 'americanism' and words
    absent from the Australian English dictionary as 'misspelling', with
    suggested corrections for each.
    """
    return _check_spelling(text)


@mcp.tool()
def check_grammar(text: str) -> dict[str, Any]:
    """Check text for grammar, punctuation and usage errors.

    Deterministic checks: 400+ curated phrase corrections (idioms, eggcorns,
    usage errors), dialect-aware a/an agreement, repeated words, spacing,
    punctuation, capitalisation and 'could of' -> 'could have'. Each issue has a
    'rule', an 'offset'/'length' span, and a 'suggestion'.

    These are advisory, high-precision rules, not a full grammatical parser:
    apply suggestions using judgment rather than blindly (a correct sentence may
    still be flagged in rare cases), and note that genuine errors needing
    sentence-level understanding may not be caught.
    """
    return _check_grammar(text)


@mcp.tool()
def get_reading_level(text: str) -> dict[str, Any]:
    """Calculate the Australian school year reading level of text.

    Returns the equivalent Australian year level, an approximate reading age,
    the Flesch-Kincaid grade and Flesch reading-ease score, plus supporting
    metrics.
    """
    return _get_reading_level(text)


def main() -> None:
    """Run the server.

    Default transport is stdio (a local client spawns this as a subprocess).
    Pass ``--http`` (or set ``MCP_TRANSPORT=http``) to serve streamable-HTTP on
    ``0.0.0.0:8000/mcp`` in stateless mode — the contract required by managed
    MCP hosts such as AWS Bedrock AgentCore Runtime. ``PORT``/``HOST`` override
    the bind address (e.g. for GCP Cloud Run, which injects ``PORT``).
    """
    http = "--http" in sys.argv or os.getenv("MCP_TRANSPORT", "").lower() in ("http", "streamable-http")
    if http:
        mcp.settings.host = os.getenv("HOST", "0.0.0.0")
        mcp.settings.port = int(os.getenv("PORT", "8000"))
        mcp.settings.stateless_http = True
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
