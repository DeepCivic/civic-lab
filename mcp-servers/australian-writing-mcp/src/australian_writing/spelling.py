"""Australian English spelling checks.

Two kinds of issue are reported:

  * ``americanism`` - a word spelled the American way that has an Australian
    equivalent (color -> colour, organize -> organise). These are detected with
    a curated map plus reliable suffix rules, each verified against the en_AU
    Hunspell dictionary so we never suggest a non-word.
  * ``misspelling`` - a word not found in the en_AU dictionary. Suggestions come
    from Hunspell.

The en_AU Hunspell dictionary (bundled under ``dictionaries/en_AU``) is the
source of truth, so spelling decisions are deterministic and offline.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from spylls.hunspell import Dictionary

_DICT_PATH = Path(__file__).parent / "dictionaries" / "en_AU" / "index"

# Common American spellings with no simple suffix rule -> Australian form.
_AMERICANISMS = {
    "color": "colour", "colors": "colours", "colored": "coloured",
    "coloring": "colouring", "honor": "honour", "honors": "honours",
    "honored": "honoured", "favor": "favour", "favors": "favours",
    "favorite": "favourite", "favorites": "favourites", "labor": "labour",
    "neighbor": "neighbour", "neighbors": "neighbours", "behavior": "behaviour",
    "behaviors": "behaviours", "flavor": "flavour", "flavors": "flavours",
    "humor": "humour", "rumor": "rumour", "vapor": "vapour", "harbor": "harbour",
    "odor": "odour", "armor": "armour", "vigor": "vigour", "savior": "saviour",
    "endeavor": "endeavour", "splendor": "splendour", "rigor": "rigour",
    "center": "centre", "centers": "centres", "centered": "centred",
    "theater": "theatre", "theaters": "theatres", "meter": "metre",
    "meters": "metres", "liter": "litre", "liters": "litres", "fiber": "fibre",
    "fibers": "fibres", "caliber": "calibre", "somber": "sombre",
    "catalog": "catalogue", "catalogs": "catalogues", "dialog": "dialogue",
    "analog": "analogue", "defense": "defence", "offense": "offence",
    "license": "licence", "pretense": "pretence", "practice": "practise",
    "gray": "grey", "tire": "tyre", "tires": "tyres", "curb": "kerb",
    "plow": "plough", "mold": "mould", "smolder": "smoulder",
    "aluminum": "aluminium", "program": "program", "jewelry": "jewellery",
    "draft": "draught", "check": "cheque", "donut": "doughnut",
    "skeptical": "sceptical", "skeptic": "sceptic", "pajamas": "pyjamas",
    "maneuver": "manoeuvre", "fetus": "foetus", "esophagus": "oesophagus",
    "cozy": "cosy", "mustache": "moustache", "airplane": "aeroplane",
}
# A few of the above (e.g. "program") are valid in both; drop self-maps.
_AMERICANISMS = {k: v for k, v in _AMERICANISMS.items() if k != v}

_WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")


@lru_cache(maxsize=1)
def _dictionary() -> Dictionary:
    return Dictionary.from_files(str(_DICT_PATH))


def _in_dict(word: str) -> bool:
    d = _dictionary()
    return bool(d.lookup(word) or d.lookup(word.lower()) or d.lookup(word.capitalize()))


def _americanism_suggestion(word: str) -> str | None:
    """Return the Australian spelling if ``word`` is a recognised americanism.

    Uses the curated map first, then -ize/-yze suffix rules. Every candidate is
    verified against the dictionary so we never produce a non-word.
    """
    lower = word.lower()
    if lower in _AMERICANISMS:
        return _match_case(word, _AMERICANISMS[lower])

    # Suffix rules: organize->organise, analyze->analyse, and inflections.
    suffix_rules = (
        ("ization", "isation"), ("izations", "isations"),
        ("ize", "ise"), ("izes", "ises"), ("ized", "ised"),
        ("izing", "ising"), ("izer", "iser"), ("izers", "isers"),
        ("yze", "yse"), ("yzes", "yses"), ("yzed", "ysed"), ("yzing", "ysing"),
    )
    for us, au in suffix_rules:
        if lower.endswith(us):
            candidate = lower[: -len(us)] + au
            if _in_dict(candidate):
                return _match_case(word, candidate)
    return None


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement.capitalize()
    return replacement


def check_spelling(text: str) -> dict:
    """Validate ``text`` against Australian English spelling.

    Returns a list of issues, each with the offending word, its character
    offset, a category (``americanism`` or ``misspelling``) and suggestions.
    """
    text = text or ""
    issues = []
    for match in _WORD_RE.finditer(text):
        word = match.group()
        if any(ch.isdigit() for ch in word):
            continue

        american = _americanism_suggestion(word)
        if american is not None:
            issues.append({
                "word": word,
                "offset": match.start(),
                "category": "americanism",
                "suggestions": [american],
                "message": f"American spelling; use Australian '{american}'.",
            })
            continue

        if _in_dict(word):
            continue

        suggestions = list(_dictionary().suggest(word))[:5]
        issues.append({
            "word": word,
            "offset": match.start(),
            "category": "misspelling",
            "suggestions": suggestions,
            "message": f"'{word}' is not in the Australian English dictionary.",
        })

    return {
        "ok": not issues,
        "issue_count": len(issues),
        "issues": issues,
    }
