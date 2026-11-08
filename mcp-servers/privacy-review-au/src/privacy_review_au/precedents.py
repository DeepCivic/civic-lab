"""Decided-case fact patterns: when does a finding match what someone did and lost?

privacy-review: ignore-file

A finding reaches the ``critical`` level only through one of these patterns, and only when:
- the condition the decisions turned on is visible in the evidence (not just the technology), and
- at least one of the decisions is final (status begins "Final" or "Stands") and is a determination,
  judgment or tribunal decision. Media releases and allegations never count.

Every match carries the decisions, the related authorities that cut the other way or are still on
review, and the questions that would distinguish the project's facts. A match is a warning that the
facts look like a losing case, not a finding that the law was contravened.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .kb import KB

DECISION_TYPES = {"determination", "judgment", "tribunal"}
FINAL = re.compile(r"^\s*(?:Final|Stands)\b", re.I)


@dataclass(frozen=True)
class Pattern:
    id: str
    title: str
    fact_pattern: str
    entry: str
    decisions: tuple[str, ...]
    related: tuple[str, ...] = ()
    detectors: frozenset[str] = frozenset()
    condition: Callable[[dict], bool] = lambda f: True
    observation: str | None = None


_IDENTIFY = re.compile(r"search_?faces|SearchFacesByImage|index_?faces|IndexFaces|identify|watch_?list|gallery|enrol|one[_-]?to[_-]?many|1:N",
                       re.I)

PATTERNS: list[Pattern] = [
    Pattern("P-FRT-IDENTIFICATION", "Facial recognition used to identify people",
            "Faces were captured and matched against stored templates without valid consent. The OAIC found 7-Eleven (faceprints "
            "from customer feedback tablets) and Clearview AI (images scraped from the internet) collected sensitive biometric "
            "information without consent.",
            "H-FRT-PROPORTIONALITY", ("aicmr-2021-50", "aicmr-2021-54"), ("aicmr-2025-155", "aicmr-2024-230", "arta-2026-130"),
            frozenset({"biometric-processing"}), lambda f: bool(_IDENTIFY.search((f.get("evidence") or "") + " " + f.get("message", ""))),
            "facial_recognition_identification"),
    Pattern("P-PIXEL-SENSITIVE", "Advertising pixels in a health or other sensitive setting",
            "Third-party advertising pixels tracked visitors to health-related websites for ad targeting. The OAIC found (Monash "
            "IVF; Medmate) that this is a collection of sensitive information that needs the visitor's consent.",
            "H-TRACKING-PIXEL-SENSITIVE", ("aicmr-2026-40", "aicmr-2026-41"), (),
            frozenset({"tracking-pixel"}), lambda f: bool((f.get("extra") or {}).get("escalated")), "tracking_pixel_sensitive"),
    Pattern("P-SCRAPING", "Scraping personal information from public sources",
            "Images and profile data were scraped from public websites and social media at scale. The OAIC found Clearview AI "
            "collected by unfair means and without consent.",
            "H-SCRAPING-PUBLIC-DATA", ("aicmr-2021-54",), (), frozenset({"scraping-personal-data"}), lambda f: True, "scraping_public_data"),
    Pattern("P-REAL-DATA-NONPROD", "Real identity or financial data outside production",
            "A dataset given to hackathon participants still held customers' personal information, despite checks meant to "
            "de-identify it. The OAIC found Flight Centre interfered with privacy.",
            "H-PROD-DATA-NON-PROD", ("aicmr-2020-57",), ("nswcatad-2021-246",),
            frozenset({"realistic-pii-in-fixtures"}), lambda f: f.get("severity") in ("high", "critical"), "real_data_in_non_production"),
    Pattern("P-HEDGED-NOTICE", "Notice that biometric collection only 'may' occur",
            "Signage said facial recognition 'may' be used. On review in Bunnings, the ART affirmed that notice of the collection "
            "was not adequately given (APP 5).",
            "R-APP5-NO-COLLECTION-NOTICE", ("arta-2026-130",), ("aicmr-2024-230",),
            frozenset({"hedged-notice-language"}), lambda f: True, "hedged_biometric_notice"),
    Pattern("P-BUNDLED-CONSENT", "Consent bundled into agreement with terms or a privacy policy",
            "Agreement to a privacy policy or terms was relied on as consent. The OAIC found in Flight Centre that bundled "
            "policy statements are not valid consent.",
            "H-CONSENT-DESIGN", ("aicmr-2020-57",), ("aicmr-2021-50",),
            frozenset({"consent-dark-patterns"}), lambda f: bool(re.search(r"I\s+agree", f.get("evidence") or "", re.I)), "bundled_consent"),
]
BY_ID = {p.id: p for p in PATTERNS}
BY_OBSERVATION = {p.observation: p for p in PATTERNS if p.observation}


def match(f: dict) -> Pattern | None:
    """The pattern a scan finding (dict) matches, if any."""
    for p in PATTERNS:
        if f.get("detector") in p.detectors and p.condition(f):
            return p
    return None


def _authority(kb: KB, sid: str, entry: dict | None) -> dict:
    s = kb.source(sid) or {}
    cites = [c for c in (entry or {}).get("citations", []) if c["source"] == sid]
    if not cites:  # fall back to any entry that cites it
        for e in kb.rules + kb.heuristics:
            cites = [c for c in e["citations"] if c["source"] == sid]
            if cites:
                break
    final = s.get("type") in DECISION_TYPES and bool(FINAL.search(s.get("status") or ""))
    return {"source": sid, "citation": s.get("citation", sid), "type": s.get("type"), "status": s.get("status", ""), "final": final,
            "propositions": [{"pinpoint": c.get("pinpoint", ""), "proposition": c["proposition"],
                              **({"quoted_from": c.get("quote_source")} if c.get("secondary") else {})} for c in cites[:2]]}


def describe(kb: KB, p: Pattern) -> dict:
    entry = kb.entry(p.entry)
    decisions = [_authority(kb, s, entry) for s in p.decisions]
    related = [_authority(kb, s, entry) for s in p.related]
    final = [d for d in decisions if d["final"]]
    return {
        "pattern": p.id, "title": p.title, "fact_pattern": p.fact_pattern, "entry": p.entry,
        "decisions": decisions, "related": related, "has_final_decision": bool(final),
        "distinguish_by": list((entry or {}).get("questions_for_agent", [])),
        "note": ("A match says the facts look like a case that was lost. Check the distinguishing questions before concluding anything."
                 if final else "The closest decisions are not final, so this is treated as high rather than critical."),
    }
