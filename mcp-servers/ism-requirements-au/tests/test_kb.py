import re

from ism_requirements_au import kb as K


def test_counts_and_release():
    kb = K.load()
    assert kb.release == "2026.09" and kb.oscal == "2026.09.4"
    assert sum(1 for _ in kb.controls()) == 1143 and sum(1 for _ in kb.controls("principle")) == 49  # 1,192 OSCAL items
    assert len(kb.rules) >= 25 and len(kb.heuristics) >= 10 and len(kb.preconditions) >= 8


def test_baselines_agree_with_oscal_profiles():
    assert all(v["agree"] for v in K.load().data["baseline_check"].values())


def test_every_referenced_control_exists_and_requirement_is_verbatim():
    kb = K.load()
    for e in kb.rules + kb.heuristics:
        for cid in e["controls"]:
            assert kb.has_control(cid), (e["id"], cid)
    for r in kb.rules:
        for req in r["requirement"]:
            assert req["statement"] == kb.control(req["control"])["statement"]
    for p in kb.preconditions:
        assert all(kb.has_control(c) for c in p["controls"])


def test_design_rule_ids_are_present():
    kb = K.load()
    wanted = ["ISM-0400", "ISM-2028", "ISM-2029", "ISM-2154", "ISM-1730", "ISM-2054", "ISM-1240", "ISM-2072", "ISM-2084", "ISM-2085", "ISM-2103",
              "ISM-2141", "ISM-2142", "ISM-2143", "ISM-1504", "ISM-2134", "ISM-1139", "ISM-1369", "ISM-0041", "ISM-0043", "ISM-1163"]
    covered = {c for e in kb.rules + kb.heuristics + [{"controls": p["controls"]} for p in kb.preconditions] for c in e["controls"]}
    assert set(wanted) <= covered, set(wanted) - covered


def test_known_control_text_and_crosswalks():
    kb = K.load()
    c = kb.control("ISM-2154")
    assert c["statement"] == "Software artefact dependencies are pinned to approved versions in source code."
    assert set(c["applicability"]) == {"NC", "OS", "P", "S", "TS"} and c["guideline"] == "Guidelines for software development"
    assert kb.control("ism-1504")["e8"], "MFA control should carry Essential Eight levels"
    assert sum(1 for c in kb.controls() if "ML2" in c["e8"]) == 87
    assert len(kb.essentials) == 58 and sum(1 for a in kb.essentials.values() if a["ism"]) == 35


def test_applicability_and_e8_mandate():
    kb = K.load()
    c = kb.control("ISM-0027")  # no TS
    assert kb.applies(c, "P") and not kb.applies(c, "TS")
    e8 = next(c for c in kb.controls() if c["e8"] and "P" not in c["applicability"]) if any(c["e8"] and "P" not in c["applicability"] for c in kb.controls()) else None
    if e8:
        assert not kb.applies(e8, "P") and kb.applies(e8, "P", "ML3")
    assert K.classification_tag("OFFICIAL: Sensitive") == "OS" and K.classification_tag("protected") == "P"


def test_quotations_are_anchored_and_attributed():
    kb = K.load()
    n = 0
    for e in kb.rules + kb.heuristics:
        for g in e["guidance"]:
            n += 1
            assert g["end"] - g["start"] == len(g["quote"]) and re.fullmatch(r"[0-9a-f]{64}", g["source_hash"])
            assert g["licence"] and g["doc"] and not (g["url"] or "").startswith("local:")
    for o in kb.obligations:
        for q in o["quotes"]:
            n += 1
            assert q["end"] - q["start"] == len(q["quote"]) and re.fullmatch(r"[0-9a-f]{64}", q["source_hash"])
    assert n >= 10
    assert any("0098" in (o["requirement_ref"] or "") for o in kb.obligations)


def test_search():
    hits = K.load().search("system security plan")
    assert hits and any(h["id"] == "ISM-0041" for h in hits)
