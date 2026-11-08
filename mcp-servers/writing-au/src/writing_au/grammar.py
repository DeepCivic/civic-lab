"""Grammar, punctuation and usage checks.

Three layers, all deterministic:

  * Phrase corrections - 400+ curated non-standard phrases (idioms, eggcorns,
    usage errors) ported from Harper's ``phrase_set_corrections`` rule set.
  * Indefinite article - dialect-aware "a"/"an" detection ported from Harper
    (handles initialisms, acronyms, and Australian pronunciation).
  * Mechanical rules - high-precision regex checks for repeated words, spacing,
    punctuation and capitalisation.

This is rule/data-driven, not a statistical parser. POS-tagger-dependent checks
(e.g. noun/verb confusion) are out of scope; see ASSESSMENT.md.
"""

from __future__ import annotations

import re

from ._phrase_data import PHRASE_CORRECTIONS
from .indefinite_article import CONSONANT, EITHER, VOWEL, starts_with_vowel_sound

_DIALECT = "australian"

# One alternation over all bad phrases, longest first so the most specific
# phrase wins at any given position.
_PHRASE_KEYS = sorted(PHRASE_CORRECTIONS, key=len, reverse=True)
_PHRASE_RE = re.compile(
    r"(?<![A-Za-z])(?:"
    + "|".join(r"\s+".join(re.escape(tok) for tok in key.split(" ")) for key in _PHRASE_KEYS)
    + r")(?![A-Za-z])",
    flags=re.IGNORECASE,
)


def _excerpt(text: str, start: int, end: int, pad: int = 20) -> str:
    s = max(0, start - pad)
    e = min(len(text), end + pad)
    return ("…" if s > 0 else "") + text[s:e].replace("\n", " ") + ("…" if e < len(text) else "")


def _add(issues, text, rule, message, start, end, suggestion=None):
    issues.append({
        "rule": rule,
        "message": message,
        "offset": start,
        "length": end - start,
        "suggestion": suggestion,
        "excerpt": _excerpt(text, start, end),
    })


def _match_case(matched: str, replacement: str) -> str:
    if matched.isupper() and any(c.isalpha() for c in matched):
        return replacement.upper()
    if matched[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _phrase_corrections(issues, text):
    for m in _PHRASE_RE.finditer(text):
        matched = m.group()
        key = re.sub(r"\s+", " ", matched.strip().lower())
        suggestions = PHRASE_CORRECTIONS.get(key)
        if not suggestions:
            continue
        cased = [_match_case(matched, s) for s in suggestions]
        primary = cased[0]
        alts = f" (or {', '.join(repr(c) for c in cased[1:])})" if len(cased) > 1 else ""
        _add(issues, text, "phrase",
             f"Consider '{primary}' instead of '{matched}'.{alts}",
             m.start(), m.end(), suggestion=primary)


def _indefinite_article(issues, text):
    for m in re.finditer(r"(?<![A-Za-z])([Aa]n?)\s+([A-Za-z][A-Za-z0-9'’-]*)", text):
        article = m.group(1).lower()
        nxt = re.split(r"[^A-Za-z0-9]", m.group(2))[0] or m.group(2)
        sound = starts_with_vowel_sound(nxt, _DIALECT)
        if sound is None or sound == EITHER:
            continue
        correct = "an" if sound == VOWEL else "a"
        if article != correct:
            _add(issues, text, "a_an",
                 f"Use '{_match_case(m.group(1), correct)}' before '{m.group(2)}'.",
                 m.start(1), m.end(1), suggestion=_match_case(m.group(1), correct))


def _mechanical(issues, text):
    # Repeated word: "the the".
    for m in re.finditer(r"\b(\w+)\s+\1\b", text, flags=re.IGNORECASE):
        _add(issues, text, "repeated_word",
             f"Repeated word '{m.group(1)}'.", m.start(), m.end(), suggestion=m.group(1))

    # "could of" -> "could have".
    for m in re.finditer(r"\b(could|would|should|must|might)\s+of\b", text, flags=re.IGNORECASE):
        verb = m.group(1)
        _add(issues, text, "modal_of",
             f"'{verb} of' should be '{verb} have'.", m.start(), m.end(),
             suggestion=f"{verb} have")

    # Double spaces between words.
    for m in re.finditer(r"\S(  +)\S", text):
        _add(issues, text, "multiple_spaces",
             "Multiple consecutive spaces.", m.start(1), m.end(1), suggestion=" ")

    # Space before punctuation.
    for m in re.finditer(r"\s+([,.;:!?])", text):
        _add(issues, text, "space_before_punctuation",
             f"Remove the space before '{m.group(1)}'.", m.start(), m.end(),
             suggestion=m.group(1))

    # Missing space after sentence punctuation (skip decimals like 3.14).
    for m in re.finditer(r"([,;:!?]|\.(?!\d))([A-Za-z])", text):
        _add(issues, text, "missing_space_after_punctuation",
             f"Add a space after '{m.group(1)}'.", m.start(), m.end(),
             suggestion=f"{m.group(1)} {m.group(2)}")

    # Repeated punctuation (allow "..." ellipsis).
    for m in re.finditer(r"([!?,;:])\1+|\.{4,}", text):
        _add(issues, text, "repeated_punctuation",
             "Repeated punctuation.", m.start(), m.end(), suggestion=m.group(0)[0])

    # Sentence not starting with a capital letter.
    for m in re.finditer(r"(?:^|[.!?]\s+)([a-z])", text):
        _add(issues, text, "sentence_capitalisation",
             f"Sentence should start with a capital letter ('{m.group(1).upper()}').",
             m.start(1), m.end(1), suggestion=m.group(1).upper())


def check_grammar(text: str) -> dict:
    """Run all grammar checks over ``text`` and return found issues."""
    text = text or ""
    issues = []
    _phrase_corrections(issues, text)
    _indefinite_article(issues, text)
    _mechanical(issues, text)
    issues.sort(key=lambda i: i["offset"])
    return {
        "ok": not issues,
        "issue_count": len(issues),
        "issues": issues,
    }
