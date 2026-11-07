import re
from pathlib import Path

import pytest

from au_privacy_review import kb as _kb
from au_privacy_review import threshold as T
from au_privacy_review.scan.scanner import scan_path

FIX = Path(__file__).parent / "fixtures"
KB = _kb.load()


def scan(p):
    return scan_path(KB, p, use_git=False)


def test_bad_fixture_recommends_pia_and_agency_requires_it():
    s = scan(FIX / "bad")
    org = T.assess(KB, s)
    assert org["outcome"] == "pia_recommended"
    assert {"sensitive_information", "biometrics_or_surveillance", "automated_decisions"} <= set(org["factors"]["high"])
    agency = T.assess(KB, s, entity_type="agency")
    assert agency["outcome"] == "pia_required"
    pins = {c["pinpoint"] for c in agency["agency_obligation"]["citations"]}
    assert {"s 12(1)", "s 12(2)"} <= pins
    assert all(c["verified"] for c in agency["agency_obligation"]["citations"] + agency["citations"])


def test_agency_with_no_change_is_not_forced():
    r = T.assess(KB, scan(FIX / "bad"), {"new_or_changed_handling": False}, entity_type="agency")
    assert r["outcome"] == "pia_recommended" and "existing PIA" in r["agency_obligation"]["assessment"]


def test_clean_fixture_needs_team_answers_then_not_indicated():
    s = scan(FIX / "clean")
    r = T.assess(KB, s)
    assert r["outcome"] == "undetermined"
    assert set(r["factors"]["unanswered"]) >= {"new_or_changed_handling", "large_scale"}
    team = {q["id"]: False for q in T.questions() if not q["detectable_from_code"]}
    r = T.assess(KB, s, team)
    assert r["outcome"] == "pia_not_indicated"


def test_stated_answer_overrides_and_conflict_flagged():
    r = T.assess(KB, scan(FIX / "bad"), {"biometrics_or_surveillance": False})
    q = next(q for q in r["questions"] if q["id"] == "biometrics_or_surveillance")
    assert q["answer"] == "no" and "conflict" in q


def test_answers_only_without_scan():
    r = T.assess(KB, None, {"handles_personal_information": True, "large_scale": True})
    assert r["outcome"] == "pia_recommended"
    r = T.assess(KB, None, {"handles_personal_information": False})
    assert r["outcome"] == "pia_not_indicated"


def test_one_medium_factor_is_targeted_review():
    team = {q["id"]: False for q in T.questions()}
    team.update({"handles_personal_information": True, "overseas_disclosure": True})
    assert T.assess(KB, None, team)["outcome"] == "targeted_review"


def test_unknown_answer_id_rejected():
    with pytest.raises(ValueError):
        T.assess(KB, None, {"not_a_question": True})


def test_report_markdown_has_sections():
    md = T.assess(KB, scan(FIX / "bad"), project_name="QuokkaCare", project_description="Telehealth bookings.")["report_markdown"]
    for h in ("# Privacy threshold assessment: QuokkaCare", "## 2. Outcome", "## 3. Threshold questions", "## 4. Personal information inventory",
              "## 5. Issues to carry into the PIA", "## 8. Legal basis", "## 9. Sign-off", "Telehealth bookings."):
        assert h in md, h
    assert "Privacy Act 1988 (Cth) s 33D(3)" in md


def test_digital_id_not_detected_by_default_and_no_digid_links():
    s = scan(FIX / "bad")
    assert s["context"]["digital_id_terms"] == []
    assert not any(e["id"].startswith("R-DIGID-") for f in s["findings"] for e in f["kb"])
    q = next(q for q in T.assess(KB, s)["questions"] if q["id"] == "digital_id_system")
    assert q["answer"] == "not detected"


def test_digital_id_accredited_links_rules_and_cites_act():
    s = scan_path(KB, FIX / "bad", use_git=False, digital_id_role="accredited_entity")
    linked = {e["id"] for f in s["findings"] for e in f["kb"] if e["id"].startswith("R-DIGID-")}
    assert {"R-DIGID-BIOMETRIC-EXPRESS-CONSENT", "R-DIGID-NO-PROFILING"} <= linked
    for f in s["findings"]:
        if any(e["id"] == "R-DIGID-PROHIBITED-ATTRIBUTES" for e in f["kb"]):  # s 44 never attaches to health-only fields
            assert any(re.search(r"ethnic|racial|religio|political|sexual|indigenous", x, re.I) for x in f["extra"]["fields"])
    r = T.assess(KB, s, digital_id_role="accredited_entity")
    q = next(q for q in r["questions"] if q["id"] == "digital_id_system")
    assert q["answer"] == "yes" and r["outcome"] == "pia_recommended"
    pins = {(c["source"], c["pinpoint"]) for c in r["citations"]}
    assert ("digital-id-act-2024", "s 28(2)(b)") in pins and ("digital-id-act-2024", "s 35") in pins
    assert any(o["id"] == "R-DIGID-UNIQUE-IDENTIFIER" for o in r["open_questions"])
    assert all(c["verified"] for c in r["citations"])


def test_digital_id_relying_party_alone_recommends_pia():
    team = {q["id"]: False for q in T.questions() if q["id"] != "digital_id_system"}
    team["handles_personal_information"] = True
    r = T.assess(KB, None, team, digital_id_role="relying_party")
    assert r["outcome"] == "pia_recommended" and "digital_id_system" in r["factors"]["high"]
    assert any(o["id"] == "R-DIGID-VOLUNTARY" for o in r["open_questions"])
    assert T.assess(KB, None, team, digital_id_role="none")["outcome"] == "pia_not_indicated"
    with pytest.raises(ValueError):
        T.assess(KB, None, team, digital_id_role="identity_provider")


def test_digital_id_detected_from_readme_and_hosts(tmp_path):
    (tmp_path / "README.md").write_text("# Sign in\nUsers verify with myID through the Australian Government Digital ID System.\n")
    (tmp_path / "auth.ts").write_text('const ISSUER = "https://auth.myid.gov.au/oidc";\n')
    (tmp_path / "webauthn.ts").write_text("// relying party id for passkeys\nconst rpId = 'example.com';\n")
    s = scan(tmp_path)
    assert {"myID", "Australian Government Digital ID System", "auth.myid.gov.au"} <= set(s["context"]["digital_id_terms"])
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "webauthn.ts").write_text("// WebAuthn relying party\nconst myId = 1;\n")
    assert scan(lib)["context"]["digital_id_terms"] == []


def test_large_scale_raises_soci_question_with_verified_citations():
    r = T.assess(KB, None, {"handles_personal_information": True, "large_scale": True})
    assert any(o["id"] == "large_scale" and "s 12F" in o["question"] for o in r["open_questions"])
    soci = [c for c in r["citations"] if c["source"] == "soci-act-2018"]
    assert {c["pinpoint"] for c in soci} == {"s 5 'business critical data'", "s 12F(1)(b)"} and all(c["verified"] for c in soci)
    assert "Security of Critical Infrastructure Act 2018 (Cth)" in r["report_markdown"]


def test_adjacent_material_in_kb_is_verified():
    ids = {e["id"] for e in KB.rules}
    assert {"R-DIGID-BIOMETRIC-EXPRESS-CONSENT", "R-DIGID-NO-PROFILING", "R-DIGID-PROHIBITED-ATTRIBUTES",
            "R-DIGID-UNIQUE-IDENTIFIER", "R-DIGID-VOLUNTARY"} <= ids
    breach = KB.entry("H-BREACH-ASSESSMENT-READINESS")
    assert {c["source"] for c in breach["also_consider"]} == {"soci-act-2018", "cyber-security-act-2024"}
    assert all(c["verified"] for c in breach["also_consider"])
    assert not any(c["source"] in ("soci-act-2018", "cyber-security-act-2024") for c in breach["citations"])
    ident = KB.entry("H-IDENTIFIERS-ARE-PERSONAL")
    assert any(c["source"] == "tia-act-1979" and c["pinpoint"] == "s 187LA(2)" and c["verified"] for c in ident["citations"])
