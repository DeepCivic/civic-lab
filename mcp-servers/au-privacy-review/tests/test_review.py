from pathlib import Path

import pytest

from au_privacy_review import kb as _kb
from au_privacy_review import observations as O
from au_privacy_review import precedents as P
from au_privacy_review import review as R
from au_privacy_review import threshold as T

FIX = Path(__file__).parent / "fixtures"
KB = _kb.load()

DESIGN = """# Visitor Insights: solution design
We will deploy cameras at all 40 sites and use facial recognition to match visitors against a watchlist
of banned customers. We will also combine loyalty data with data purchased from a broker to build
customer profiles, and send records to our US analytics vendor.
The system replaces the existing manual process and covers around 2 million customers nationally.
"""


def build(path=None, **kw):
    return R.build(KB, path, use_git=False, **kw)


def by_detector(rv, det):
    return [f for f in rv["findings"] if f["detector"] == det]


def test_bad_fixture_levels():
    rv = build(FIX / "bad")["review"]
    crit = {f["precedent"]["pattern"] for f in rv["findings"] if f["level"] == "critical"}
    assert {"P-PIXEL-SENSITIVE", "P-REAL-DATA-NONPROD", "P-HEDGED-NOTICE"} <= crit
    # face-value rule findings with firm evidence are high
    assert by_detector(rv, "weak-password-hashing")[0]["level"] == "high"
    assert by_detector(rv, "iac-public-storage")[0]["level"] == "high"
    # a heuristic with no decided authority (MFA) and a low-confidence guess (automated decisions) are cautions
    assert by_detector(rv, "mfa-disabled")[0]["level"] == "caution"
    assert by_detector(rv, "automated-decision")[0]["level"] == "caution"
    # findings are ordered by level and carry what to confirm
    order = [R.LEVELS.index(f["level"]) for f in rv["findings"]]
    assert order == sorted(order, reverse=True)
    assert all(f.get("to_confirm") for f in rv["findings"] if f["level"] == "critical")
    assert any(g["type"] == "distinguishing_facts" for g in rv["gaps"])


def test_critical_needs_a_final_decision():
    for p in P.PATTERNS:
        d = P.describe(KB, p)
        assert d["has_final_decision"], p.id  # every shipped pattern rests on at least one final decision
        assert all(x["type"] in P.DECISION_TYPES for x in d["decisions"] if x["final"])
    # a pattern resting only on a non-final authority is high, not critical
    kmart = P.Pattern("P-TEST", "t", "t", "H-FRT-PROPORTIONALITY", ("aicmr-2025-155",))
    f = {"severity": "high", "precedent": P.describe(KB, kmart), "kb": []}
    assert R._level(f, None) == "high"


def test_biometric_verification_is_not_matched_to_identification_cases(tmp_path):
    (tmp_path / "verify.py").write_text("import face_recognition\nok = face_recognition.compare_faces([enrolled], probe)\n")
    rv = build(tmp_path)["review"]
    f = by_detector(rv, "biometric-processing")[0]
    assert "precedent" not in f and f["level"] == "high"  # sensitive information without consent capture, on its face
    (tmp_path / "match.py").write_text("client.search_faces_by_image(CollectionId='watchlist', Image=img)\n")
    rv = build(tmp_path)["review"]
    assert any(f.get("precedent", {}).get("pattern") == "P-FRT-IDENTIFICATION" for f in by_detector(rv, "biometric-processing"))


def test_sdk_recipients_alone_do_not_recommend_a_pia(tmp_path):
    (tmp_path / "package.json").write_text('{"name":"shop","dependencies":{"stripe":"^14","@sentry/node":"^7"}}')
    (tmp_path / "app.js").write_text('import Stripe from "stripe";\nimport * as Sentry from "@sentry/node";\n')
    b = build(tmp_path)
    assert b["threshold"]["outcome"] == "undetermined"
    assert any("none was confirmed" in r for r in b["threshold"]["reasons"])
    # once personal information is confirmed, two code-detected recipient factors still count once
    team = {q["id"]: False for q in T.questions() if not q["detectable_from_code"]}
    team["handles_personal_information"] = True
    assert build(tmp_path, answers=team)["threshold"]["outcome"] == "targeted_review"


def test_documents_are_read_not_treated_as_absent(tmp_path):
    (tmp_path / "design.md").write_text(DESIGN)
    b = build(None, documents=[tmp_path])
    rows = {r["id"]: r for r in b["threshold"]["questions"]}
    for q in ("biometrics_or_surveillance", "large_scale", "indirect_collection", "overseas_disclosure", "new_or_changed_handling"):
        assert rows[q]["answer"] == "indicated", q
    assert rows["government_identifiers"]["answer"] == "unknown"  # no code examined: never 'not detected'
    rv = b["review"]
    assert by_detector(rv, "document-mention") and all(f["level"] == "caution" for f in by_detector(rv, "document-mention"))
    assert b["threshold"]["outcome"] == "undetermined"
    assert any(g["id"] == "no-code" for g in rv["gaps"])
    gap = next(g for g in rv["gaps"] if g["id"] == "large_scale")
    assert gap["status"] == "indicated" and gap["what_would_resolve"] and "large_scale" in gap["record_as"]


def test_observations_answer_questions_and_match_precedent(tmp_path):
    (tmp_path / "design.md").write_text(DESIGN)
    obs = [{"kind": "facial_recognition_identification", "fact": "Visitors matched against a banned-customer watchlist",
            "source": "design.md:2"},
           {"kind": "large_scale", "fact": "About 2 million customers", "source": "design.md:5"},
           {"kind": "overseas_disclosure", "fact": "No data leaves Australia", "source": "team", "present": False}]
    b = build(None, documents=[tmp_path], observations=obs)
    rv, rows = b["review"], {r["id"]: r for r in b["threshold"]["questions"]}
    crit = [f for f in rv["findings"] if f["level"] == "critical"]
    assert crit and crit[0]["precedent"]["pattern"] == "P-FRT-IDENTIFICATION" and crit[0]["file"] == "design.md:2"
    assert {d["source"] for d in crit[0]["precedent"]["decisions"] if d["final"]} == {"aicmr-2021-50", "aicmr-2021-54"}
    assert rows["biometrics_or_surveillance"]["answer"] == "yes" and rows["sensitive_information"]["answer"] == "yes"
    assert rows["overseas_disclosure"]["answer"] == "no" and "team" in rows["overseas_disclosure"]["basis"]
    assert b["threshold"]["outcome"] == "pia_recommended"
    # an observed kind suppresses the document-mention finding for it
    assert not any(f.get("observation_kind") == "large_scale" for f in rv["findings"])


def test_observation_validation():
    with pytest.raises(ValueError, match="unknown kind"):
        O.normalise([{"kind": "nope", "fact": "x"}])
    with pytest.raises(ValueError, match="fact"):
        O.normalise([{"kind": "large_scale"}])
    with pytest.raises(ValueError, match="unknown question"):
        O.normalise([], {"not_a_question": True})
    assert {k["kind"] for k in O.kinds()} >= {p.observation for p in P.PATTERNS}
    for k in O.KINDS:
        assert k.question is None or k.question in T.QUESTION_IDS
        assert all(KB.entry(e) for e in k.entries), k.id
        assert k.precedent is None or k.precedent in P.BY_ID


def test_negated_and_policy_text_are_not_mentions(tmp_path):
    (tmp_path / "notes.md").write_text("We do not send any data overseas. No facial recognition is used.\n")
    (tmp_path / "privacy-policy.md").write_text("We may disclose personal information to overseas recipients.\n")
    (tmp_path / "app.py").write_text("x = 1\n")
    s = build(tmp_path)["review"]
    assert "overseas_disclosure" not in s["document_mentions"] and "biometric_processing" not in s["document_mentions"]


def test_unread_documents_become_a_gap(tmp_path):
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "Solution Design.pdf").write_bytes(b"%PDF-1.7")
    rv = build(tmp_path)["review"]
    assert rv["coverage"]["unread_documents"] == ["Solution Design.pdf"]
    g = next(g for g in rv["gaps"] if g["id"] == "unread-documents")
    assert g["priority"] == "high" and "observations" in g["what_would_resolve"]


def test_interrogate(tmp_path):
    (tmp_path / "design.md").write_text(DESIGN)
    b = build(None, documents=[tmp_path])
    q = R.interrogate(KB, b, "data_matching_or_linkage")
    assert q["type"] == "threshold_question" and q["row"]["answer"] == "indicated" and q["document_mentions"]["data_matching"]
    assert R.interrogate(KB, b, "H-FRT-PROPORTIONALITY")["precedent_patterns"][0]["pattern"] == "P-FRT-IDENTIFICATION"
    assert R.interrogate(KB, b, "scraping_public_data")["precedent"]["pattern"] == "P-SCRAPING"
    fid = b["review"]["findings"][0]["id"]
    assert R.interrogate(KB, b, fid)["type"] == "finding"
    with pytest.raises(ValueError):
        R.interrogate(KB, b, "nonsense")


def test_report_markdown(tmp_path):
    md = build(FIX / "bad")["review"]["report_markdown"]
    for h in ("# Privacy review: bad", "## Critical", "## High", "## Caution", "## Open questions", "## Threshold readiness",
              "Resembles:", "Monash IVF"):
        assert h in md, h
