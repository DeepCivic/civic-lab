"""Deterministic, explainable name matching.

No model, no learned weights, no probability. A candidate name is compared with the subject's
name in fixed tiers, and each tier has a plain-English reason that is returned with the match.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# Words that say what kind of company something is, not which one. Ignored when comparing names
# so "Example Widgets" finds "EXAMPLE WIDGETS PTY LTD". Geography words and "group" are kept,
# because they separate real entities.
LEGAL_FORM = frozenset("pty ltd limited proprietary inc incorporated llc plc co company corp corporation the".split())
FUZZY_THRESHOLD = 0.9
FUZZY_MIN_LENGTH = 6

TIER_EXACT, TIER_WORDS, TIER_SIMILAR = 3, 2, 1


def norm(text: str) -> str:
    """Fold case, accents, punctuation and '&', so only the words remain."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold().replace("&", " and ")
    return re.sub(r"[\W_]+", " ", t).strip()


def _core(n: str) -> str:
    kept = [w for w in n.split() if w not in LEGAL_FORM]
    return " ".join(kept) if kept else n


@dataclass(frozen=True, slots=True)
class Name:
    record_id: str
    field: str  # which field of the record this name came from
    display: str
    norm: str
    core: str
    tokens: frozenset[str]
    ordered: str  # core words sorted, for order-insensitive comparison


def make_name(record_id: str, field: str, display: str) -> Name | None:
    n = norm(display)
    if not n:
        return None
    c = _core(n)
    toks = frozenset(c.split())
    return Name(record_id, field, display, n, c, toks, " ".join(sorted(toks)))


class Query:
    def __init__(self, text: str):
        self.text = text
        n = norm(text)
        self.norm, self.core = n, _core(n)
        self.tokens = frozenset(self.core.split())
        self.ordered = " ".join(sorted(self.tokens))
        self._sm = difflib.SequenceMatcher(None, autojunk=False)
        self._sm.set_seq2(self.ordered)

    @property
    def usable(self) -> bool:
        return len(self.core.replace(" ", "")) >= 3

    def compare(self, c: Name) -> tuple[int, str] | None:
        if self.norm == c.norm:
            return TIER_EXACT, "same name after ignoring case, accents and punctuation"
        if self.core == c.core:
            return TIER_EXACT, "same name apart from company-type words (Pty, Ltd, Inc, ...)"
        if self.ordered == c.ordered:
            return TIER_EXACT, "same words in a different order"
        small, large = sorted((self.tokens, c.tokens), key=len)
        if len(small) >= 2 and small <= large:
            return TIER_WORDS, "every word of the shorter name appears in the longer name"
        if min(len(self.ordered), len(c.ordered)) >= FUZZY_MIN_LENGTH:
            sm = self._sm
            sm.set_seq1(c.ordered)
            if (sm.real_quick_ratio() >= FUZZY_THRESHOLD and sm.quick_ratio() >= FUZZY_THRESHOLD
                    and sm.ratio() >= FUZZY_THRESHOLD):
                return TIER_SIMILAR, f"similar spelling ({sm.ratio():.0%} of characters agree)"
        return None


def best_by_record(query: Query, names: list[Name], allowed: set[str] | None = None) -> dict[str, list[tuple[int, str, Name]]]:
    """Every name that matches, grouped by record, strongest first."""
    hits: dict[str, list[tuple[int, str, Name]]] = {}
    for c in names:
        if allowed is not None and c.record_id not in allowed:
            continue
        r = query.compare(c)
        if r:
            hits.setdefault(c.record_id, []).append((r[0], r[1], c))
    for v in hits.values():
        v.sort(key=lambda h: -h[0])
    return hits


def alnum(text: str) -> str:
    return re.sub(r"[^0-9A-Z]", "", unicodedata.normalize("NFKD", text).upper())


def id_tokens(text: str) -> list[str]:
    """The letter-and-digit runs of a text, upper-cased, in order: "Passport no. FX 123-4567" gives
    ["PASSPORT", "NO", "FX", "123", "4567"]."""
    t = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).upper()
    return re.findall(r"[0-9A-Z]+", t)


def has_identifier(tokens: list[str], ident: str) -> bool:
    """Whether `ident` (as alnum() gives it) is one whole run, or several adjacent runs written with
    spaces or punctuation between them. It must start and end on a run boundary, so part of a
    longer number never matches: "012345" is not found in "7012345678"."""
    for i in range(len(tokens)):
        acc = ""
        for tok in tokens[i:]:
            acc += tok
            if acc == ident:
                return True
            if not ident.startswith(acc):
                break
    return False


def years(text: str | None) -> set[int]:
    return {int(y) for y in re.findall(r"\b(1[89]\d\d|20\d\d)\b", text or "")}


def evidence(field: str, subject_value: str, record_value: str, method: str) -> dict[str, Any]:
    return {"field": field, "subject_value": subject_value, "record_value": record_value, "method": method}
