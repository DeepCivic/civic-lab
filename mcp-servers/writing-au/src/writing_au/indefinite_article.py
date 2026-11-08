"""Indefinite-article ("a" vs "an") detection, ported from Harper.

This is a faithful Python port of Harper's ``starts_with_vowel`` logic
(harper-core/src/indefinite_article.rs, Apache-2.0). It decides whether a word
begins with a vowel *sound* — handling initialisms ("an SQL" vs "a SQL"),
acronyms ("a NASA"), and dialect-specific cases ("herb") — rather than just a
vowel letter. See NOTICE for attribution.
"""

from __future__ import annotations

# Dialects that pronounce a silent "h" in "herb" (so it takes "an").
_H_DROPPING_DIALECTS = {"american", "canadian"}

# Letters whose *name* begins with a vowel sound (F = "eff", H = "aitch", etc.).
_VOWEL_SOUND_LETTERS = set("AEFHILMNORSX")

VOWEL = "vowel"
CONSONANT = "consonant"
EITHER = "either"


def _is_vowel(ch: str) -> bool:
    return ch.lower() in "aeiou"


def _likely_acronym(word: str) -> bool:
    """A pronounceable initialism (e.g. NASA) read as a word, not letter-by-letter."""
    if len(word) < 3 or not word[:3].isalpha():
        return False
    if "VC" in word:  # known false-positive sequence
        return False
    vmap = tuple(_is_vowel(c) for c in word[:3])
    return vmap in ((False, True, False), (False, True, True))


def _partial_initialism(word: str) -> str:
    """Return the leading initialism chunk, e.g. 'RFL' from 'RFLink', 'm' from 'mDNS'."""
    if len(word) < 2 or not word[0].isalpha() or not word[1].isalpha():
        return word
    if not word[1].isupper():
        return word
    first_upper = word[0].isupper()
    for i, c in enumerate(word):
        if not c.isalpha() or c.isupper() != first_upper:
            return word[:i]
    return word


def starts_with_vowel_sound(word: str, dialect: str = "australian") -> str | None:
    """Return VOWEL, CONSONANT, or EITHER for ``word`` (None if empty)."""
    if not word:
        return None
    dialect = dialect.lower()

    if word in ("LED", "SQL", "URL"):
        return EITHER

    word = _partial_initialism(word)

    is_initialism = all((not c.isalpha()) or c.isupper() for c in word)
    if len(word) == 1 or (is_initialism and not _likely_acronym(word)):
        return VOWEL if word[0].upper() in _VOWEL_SOUND_LETTERS else CONSONANT

    w = word.lower()

    def sw(*prefixes: str) -> bool:
        return any(w.startswith(p) for p in prefixes)

    if sw("ubi"):
        return EITHER
    if sw("eule"):
        return VOWEL
    if sw("uk", "ude", "euph", "eug", "eul", "euc", "one") or w == "once":
        return CONSONANT
    if sw("hour", "unin", "unim", "una", "unu", "urb", "int"):
        return VOWEL
    if w.startswith("herb") and dialect in _H_DROPPING_DIALECTS:
        return VOWEL
    if sw("uni", "una", "unu", "usi", "usa", "usu"):
        return CONSONANT
    if w.startswith("un"):
        return VOWEL
    if sw("urg", "utt"):
        return VOWEL
    if sw("ut", "ur", "un", "eur", "uw", "use"):
        return CONSONANT
    # "one" + (a/e/i/u) + (l/d): vowel (e.g. "oneuld"? rare); else consonant.
    if len(w) >= 5 and w[:3] == "one" and w[3] in "aeiu" and w[4] in "ld":
        return VOWEL
    if len(w) >= 4 and w[:3] == "one" and w[3] in "aeiu-s":
        return CONSONANT
    if w in ("sos",) or sw("rz", "ng", "nv", "xbox", "heir", "honor", "hones"):
        return VOWEL
    if sw("jun", "jon") or (len(w) >= 4 and w[:2] == "ju" and w[2] == "r" and w[3] in "aio"):
        return CONSONANT
    if len(w) >= 2 and w[0] == "x" and w[1] in "-'.os":
        return VOWEL

    return VOWEL if _is_vowel(w[0]) else CONSONANT
