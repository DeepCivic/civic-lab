import csv
import io

import pytest
import yaml

from ism_requirements_au import annex as A
from ism_requirements_au import kb as K
from ism_requirements_au import server
from ism_requirements_au import track as T
from ism_requirements_au.server import ToolError


def manifest_for(project, controls):
    (project / ".ism").mkdir(exist_ok=True)
    m = {"ism_release": "2026.09", "scope": {"classification": "PROTECTED", "e8_target": "ML2"}, "controls": controls}
    (project / ".ism/controls.yaml").write_text(yaml.safe_dump(m), encoding="utf-8")


def good_entry(cid="ISM-2154", **kw):
    e = {"id": cid, "text_sha256": T.text_sha256(K.load().control(cid)["statement"]), "status": "implemented", "fidelity": "direct",
         "mechanism": {"kind": "ci", "ref": ".github/workflows/ci.yml"}, "evidence": ["requirements.txt"]}
    return {**e, **kw}


def test_plan_entry_roundtrip():
    p = T.plan(K.load(), "PROTECTED", "ML2", ["Identity services"])
    m = T.parse(p["yaml"])
    assert m["ism_release"] == "2026.09" and m["scope"]["essentials_domains"] == ["Identity services"] and m["controls"]
    assert all(c["text_sha256"] == T.text_sha256(K.load().control(c["id"])["statement"]) for c in m["controls"])
    e = T.entry(K.load(), "ism-2154", "implemented", "ci", ".github/workflows/ci.yml", ["requirements.txt"], "direct")
    assert not e["warnings"] and yaml.safe_load(e["yaml"])[0]["id"] == "ISM-2154"
    assert T.entry(K.load(), "ISM-2154", "implemented", fidelity="direct")["warnings"]
    with pytest.raises(ValueError):
        T.entry(K.load(), "ISM-9999", "planned")
    with pytest.raises(ValueError):
        T.entry(K.load(), "ISM-2154", "done")


def test_verify_ok_and_errors(clean_repo, tmp_path):
    import shutil

    proj = tmp_path / "p"
    shutil.copytree(clean_repo, proj)
    manifest_for(proj, [good_entry()])
    assert T.verify(K.load(), proj)["ok"]
    manifest_for(proj, [good_entry(text_sha256="0" * 64), good_entry("ISM-0400", evidence=["nope.txt"], fidelity="supporting"),
                        {"id": "ISM-9999", "status": "planned"}, good_entry(fidelity="direct", mechanism={"kind": "ci", "ref": ""})])
    r = T.verify(K.load(), proj)
    text = "\n".join(r["errors"])
    assert not r["ok"] and "text_sha256" in text and "does not exist" in text and "not a control" in text and "without a mechanism" in text and "duplicate" in text


def test_verify_markers_and_strict(clean_repo, tmp_path):
    import shutil

    proj = tmp_path / "p"
    shutil.copytree(clean_repo, proj)
    (proj / "code.py").write_text("# ism: ISM-0400\n", encoding="utf-8")
    manifest_for(proj, [good_entry()])
    assert "no manifest entry" in "\n".join(T.verify(K.load(), proj)["errors"])
    manifest_for(proj, [good_entry(), good_entry("ISM-0400")])
    assert T.verify(K.load(), proj)["ok"]
    assert any("strict" in e for e in T.verify(K.load(), proj, strict=True)["errors"])
    assert not T.verify(K.load(), tmp_path / "empty")["ok"]


def test_verify_is_deterministic(clean_repo, tmp_path):
    import shutil

    proj = tmp_path / "p"
    shutil.copytree(clean_repo, proj)
    manifest_for(proj, [good_entry(), good_entry("ISM-0400", status="partial", fidelity="supporting")])
    assert T.verify(K.load(), proj) == T.verify(K.load(), proj)


def test_evidence_cannot_escape_project(clean_repo, tmp_path):
    import shutil

    proj = tmp_path / "p"
    shutil.copytree(clean_repo, proj)
    manifest_for(proj, [good_entry(evidence=["../../etc/passwd"])])
    assert "escapes" in "\n".join(T.verify(K.load(), proj)["errors"])


def test_gaps_and_impact():
    kb = K.load()
    changed = good_entry("ISM-2154", text_sha256="1" * 64, reviewed_against="2026.06")
    m = {"scope": {"classification": "PROTECTED"}, "controls": [changed, good_entry("ISM-0400", status="implemented", mechanism={"kind": "ci", "ref": ""}, evidence=[], fidelity="supporting")]}
    g = T.gaps(kb, m)
    assert any(x["id"] == "ISM-0400" for x in g["weak_entries"]) and g["undeclared_rule_controls"] and g["applicable_not_declared"] > 100
    i = T.impact(kb, m)
    assert i["changed"] and i["changed"][0]["id"] == "ISM-2154"
    with pytest.raises(ValueError):
        T.gaps(kb, {"controls": []})


def test_annex_schema_and_draft():
    s = A.schema()
    assert len(s["controls_sheet_columns"]) == 20 and "Not Assessed" in s["value_lists"]["Assessment Outcome"]
    m = {"scope": {"classification": "PROTECTED", "e8_target": "ML2"}, "controls": [
        good_entry("ISM-2154", responsibility="System Owner", source="Self-Implemented"),
        good_entry("ISM-0400", status="partial", note="staging not yet separate"),
        good_entry("ISM-1730", status="not_applicable")]}
    d = A.draft(K.load(), m)
    rows = {r["Identifier"]: r for r in csv.DictReader(io.StringIO(d["csv"]))}
    assert rows["ISM-2154"]["Implementation Status"] == "Implemented" and rows["ISM-2154"]["Responsibility"] == "System Owner"
    assert rows["ISM-0400"]["Implementation Status"] == "Not Determined" and "partial" in rows["ISM-0400"]["Assessment Comments"]
    assert rows["ISM-1730"]["Implementation Status"] == "Not Applicable"
    assert {r["Assessment Outcome"] for r in rows.values()} == {"Not Assessed"}
    assert set(rows["ISM-2054"].values()) - {"ISM-2054", "Not Determined", "Not Assessed", ""} == set()
    assert "ISM-0027" in rows and d["template"].startswith("Identifying columns")
    assert "Assessment Comments" not in A.draft(K.load(), m, include_comments=False, fmt="json")["columns"]
    assert len(A.draft(K.load(), m, sections=["Software development fundamentals"])["csv"].splitlines()) < len(d["csv"].splitlines())
    assert A.draft(K.load(), m, sheet="principles")["rows"] == 49


def test_tracking_tools_over_mcp(clean_repo, tmp_path):
    import shutil

    proj = tmp_path / "p"
    shutil.copytree(clean_repo, proj)
    manifest_for(proj, [good_entry()])
    assert server.track_impact(project=str(proj))["changed"] == []
    assert server.track_gaps(project=str(proj))["undeclared_rule_controls"]
    assert server.draft_ssp_annex(project=str(proj))["tracked"] == 1
    assert "verify" in server.track_ci()["yaml"] and server.ssp_annex_xlsx_instructions()
    with pytest.raises(ToolError):
        server.track_gaps(project=str(tmp_path / "nowhere"))
    with pytest.raises(ToolError):
        server.track_gaps(manifest_yaml="- not a mapping")


def test_malformed_manifest_is_an_error_not_a_crash(clean_repo, tmp_path):
    import shutil

    proj = tmp_path / "p"
    shutil.copytree(clean_repo, proj)
    (proj / ".ism").mkdir()
    (proj / ".ism/controls.yaml").write_text("ism_release: '2026.09'\nscope: {classification: PROTECTED}\ncontrols:\n  - ISM-0041\n", encoding="utf-8")
    r = T.verify(K.load(), proj)
    assert not r["ok"] and "controls[0] must be a mapping" in r["errors"][0]
    for tool in (server.track_gaps, server.track_impact, server.draft_ssp_annex):
        with pytest.raises(ToolError):
            tool(project=str(proj))
    with pytest.raises(ToolError):
        server.track_gaps(manifest_yaml="scope: PROTECTED\ncontrols: []\n")


def test_phase_is_validated(clean_repo, tmp_path):
    import shutil

    with pytest.raises(ValueError):
        T.entry(K.load(), "ISM-2154", "planned", phase="banana")
    proj = tmp_path / "p"
    shutil.copytree(clean_repo, proj)
    manifest_for(proj, [good_entry(phase="banana")])
    assert any("phase must be one of" in e for e in T.verify(K.load(), proj)["errors"])


def test_ci_workflow_does_not_assume_pypi():
    run = next(ln for ln in server.track_ci()["yaml"].splitlines() if "verify" in ln and "run:" in ln)
    assert "git+https://github.com/DeepCivic/civic-lab#subdirectory=mcp-servers/ism-requirements-au" in run
