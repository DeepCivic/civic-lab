"""Reading age / grade level mapped to the Australian school system.

textstat produces a US-grade Flesch-Kincaid score. Australian school years
align almost 1:1 with US grades (both start formal schooling at ~age 5), so we
map the grade directly to an Australian year level and an approximate reading
age (age in years is roughly grade + 5).
"""

from __future__ import annotations

import textstat


def _year_level(grade: float) -> str:
    """Map a US-equivalent grade level to an Australian school year label."""
    if grade < 1:
        return "Foundation (Prep/Kindergarten)"
    if grade > 12:
        return "Tertiary / adult"
    return f"Year {round(grade)}"


def get_reading_level(text: str) -> dict:
    """Calculate the Australian school year level for ``text``.

    Returns the Flesch-Kincaid grade, the equivalent Australian year level, an
    approximate reading age, and supporting metrics. All values are
    deterministic for a given input.
    """
    text = text or ""
    if not text.strip():
        return {
            "australian_year_level": None,
            "reading_age_years": None,
            "flesch_kincaid_grade": None,
            "flesch_reading_ease": None,
            "metrics": {"sentences": 0, "words": 0, "syllables": 0},
            "note": "No text provided.",
        }

    fk_grade = textstat.flesch_kincaid_grade(text)
    # Grade can go negative for trivial text; clamp for reporting.
    grade = max(fk_grade, 0.0)

    return {
        "australian_year_level": _year_level(grade),
        # Reading age tops out at adult (~18); beyond that it is not meaningful.
        "reading_age_years": round(min(grade, 13) + 5),
        "flesch_kincaid_grade": round(fk_grade, 1),
        "flesch_reading_ease": round(textstat.flesch_reading_ease(text), 1),
        "metrics": {
            "sentences": textstat.sentence_count(text),
            "words": textstat.lexicon_count(text),
            "syllables": textstat.syllable_count(text),
        },
        "note": (
            "Flesch-Kincaid grade is a US grade level; Australian year levels "
            "align approximately 1:1. Reading age is grade + 5 years."
        ),
    }
