"""Entity-name normalisation for conservative, deterministic matching.

``name_key`` is the comparison key used for exact-name matching and for the
full-text index. It is the rule that worked in the DeepCivic grants/procurement
alias check: upper-case, punctuation to spaces, drop a leading ``THE`` /
``THE TRUSTEE FOR`` and drop legal-form tokens (``PTY``, ``LTD`` ...), so that
``The Trustee for Acme Pty. Ltd.`` and ``ACME PTY LTD`` share a key.

It deliberately does *not* drop geography words (``AUSTRALIA``) or ``CO``:
those distinguish real entities (``ACME`` vs ``ACME AUSTRALIA``). A shared key
is a candidate match for review, never proof of identity — that is what the
ABN is for.
"""

from __future__ import annotations

import re
import unicodedata

_LEGAL_FORMS = (
    "PROPRIETARY", "PTY", "LIMITED", "LTD", "INCORPORATED", "INC", "NL",
)
_LEGAL_RE = re.compile(r"\b(?:" + "|".join(_LEGAL_FORMS) + r")\b")
_PL_RE = re.compile(r"\bP\s*/\s*L\b")
_LEAD_RE = re.compile(r"^(?:THE TRUSTEE FOR|THE)\s+")
_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_SPACES = re.compile(r"\s+")


def name_key(name: object) -> str:
    """Normalised comparison key for an entity name ("" for empty input)."""
    if name is None:
        return ""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c)).upper()
    text = text.replace("&", " AND ")
    text = _PL_RE.sub(" ", text)
    text = _NON_ALNUM.sub(" ", text)
    text = _SPACES.sub(" ", text).strip()
    text = _LEAD_RE.sub("", text)
    text = _LEGAL_RE.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def fts_query(name: object) -> str:
    """FTS5 MATCH expression: every key token, each as a quoted prefix."""
    tokens = [t for t in name_key(name).split(" ") if t]
    return " AND ".join(f'"{t}"*' for t in tokens)
