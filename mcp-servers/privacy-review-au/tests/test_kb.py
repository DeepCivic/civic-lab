"""The shipped knowledge base is internally consistent and every quote was verified at build."""

from pathlib import Path

import pytest

from privacy_review_au import kb as _kb
from privacy_review_au.scan import detectors as D

ROOT = Path(__file__).resolve().parents[1]
KB = _kb.load()
REPO_LEVEL = {"privacy-policy-missing", "privacy-policy-omits-capability", "privacy-policy-contents", "automated-decision",
              "no-retention-controls", "no-breach-runbook", "no-audit-logging", "no-pia", "data-dump-committed",
              "overseas-processor-sdk", "realistic-pii-in-fixtures", "sensitive-fields-no-consent", "excessive-fields",
              "forced-identification", "marketing-no-unsubscribe", "form-without-notice", "scraping-personal-data"}


def entries():
    return KB.rules + KB.heuristics


def test_every_citation_verified_and_anchored():
    for e in entries():
        assert e["citations"], e["id"]
        for c in e["citations"]:
            assert c.get("verified") is True, (e["id"], c["quote"][:60])
            assert len(c["anchor"]["source_hash"]) == 64 and c["anchor"]["end"] > c["anchor"]["start"]


def test_rules_cite_legislation_and_heuristics_cite_cases():
    for e in entries():
        types = {KB.source(c["source"])["type"] for c in e["citations"]}
        if e["kind"] == "rule":
            assert "legislation" in types, e["id"]
        else:
            decided = {KB.source(c["source"])["type"] for c in e["citations"] if "General only" not in c["proposition"]}
            if not decided & {"determination", "judgment", "tribunal"}:
                assert e.get("evidence_gap") and e["confidence"] == "low", e["id"]


def test_detectors_referenced_by_kb_exist():
    known = {d.id for d in D.PATTERNS} | REPO_LEVEL
    for e in entries():
        for det in e.get("detectors", []):
            assert det in known, (e["id"], det)


def test_detectors_point_at_real_entries():
    for d in D.PATTERNS:
        for eid in d.entries:
            assert KB.entry(eid), (d.id, eid)


def test_source_statuses_flag_contested_authorities():
    assert "set aside" in KB.source("aicmr-2024-230")["status"]
    assert "review" in KB.source("aicmr-2026-24")["status"]
    assert "ALLEGATIONS" in KB.source("medibank-concise")["status"]


def test_apps_present_and_future_text_dated():
    assert all(KB.app(n) for n in range(1, 14))
    assert KB.app(1)["future"]["commences"] == "2026-12-10"
    assert "technical and organisational measures" in KB.app(11)["text"]


def test_local_only_text_not_shipped():
    raw = (ROOT / "src/privacy_review_au/data/kb.json").read_text(encoding="utf-8")
    assert "lack of precision" in raw
    assert "Rehnquist CJ recently observed" not in raw


def test_coverage_only_rules_never_scan():
    for e in KB.rules:
        if e.get("coverage_only"):
            assert not e["detectors"], e["id"]


def test_every_entry_tagged_with_jurisdiction():
    assert all(e.get("jurisdictions") for e in entries())


def test_state_authorities_are_labelled_and_not_redistributed():
    state = [s for s in KB.sources() if s.get("jurisdiction") == "nsw" and s["type"] == "tribunal"]
    assert state
    for s in state:
        assert "NSW law" in s["status"] or "Appeal Panel" in s["status"] or "Varied on appeal" in s["status"] or "Telstra" in s["status"], s["id"]
        assert s["anchor_base"]["redistributable"] is False, s["id"]


def test_limiting_authority_recorded_on_prod_copy_heuristic():
    roles = {c.get("role") for c in KB.entry("H-PROD-DATA-NON-PROD")["citations"]}
    assert "limits" in roles


def test_insider_heuristic_reachable_from_scan():
    import inspect
    assert "H-INSIDER-ACCESS-SAFEGUARDS" in inspect.getsource(D.repo_level)
