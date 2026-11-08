import asyncio

import pytest

from ism_requirements_au import server
from ism_requirements_au.server import ToolError

TOOLS = {"assess_applicability", "scope_system", "review_project", "authorisation_readiness", "interrogate", "get_control", "search_controls",
         "get_obligation", "get_essentials_action", "diff_release", "ssp_annex_schema", "draft_ssp_annex", "ssp_annex_xlsx_instructions",
         "track_plan", "track_entry", "track_gaps", "track_impact", "track_ci", "kb_status"}


def test_tools_and_prompts_listed():
    assert TOOLS <= {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"ism_requirements", "irap_readiness"} <= {p.name for p in asyncio.run(server.mcp.list_prompts())}


def test_review_then_interrogate(bad_repo):
    r = server.review_project(path=str(bad_repo), entity_type="non_corporate_commonwealth", phase="assess")
    assert r["summary"]["by_level"]["blocker"] and r["findings"]["blocker"] and r["run_id"]
    top = r["findings"]["blocker"][0]
    d = server.interrogate(top["id"])
    assert d["finding"]["id"] == top["id"] and d["requirement"] and "settle" in d["finding"]
    rule = next(f for f in r["findings"]["gap"] if f["rule"].startswith("R-"))
    dd = server.interrogate(rule["id"])
    assert dd["what_non_conformance_looks_like"] and dd["remediation"]


def test_interrogate_other_kinds():
    assert server.interrogate("ISM-1504")["statement"].startswith("Multi-factor")
    assert server.interrogate("R-PINNED-DEPS")["controls"] == ["ISM-2154"]
    assert server.interrogate("PRE-IRP")["requirement"][0]["control"] == "ISM-0043"
    assert server.interrogate("PSPF-14-STRATEGY")["requirement_ref"] == "0098"
    ea = next(i for i, a in server._load().essentials.items() if a["ism"])
    assert server.interrogate(ea)["controls"]
    with pytest.raises(ToolError):
        server.interrogate("F-deadbeef")
    with pytest.raises(ToolError):
        server.interrogate("nonsense")


def test_lookup_tools():
    c = server.get_control(["ISM-0041", "ISM-9999"])
    assert c[0]["baselines"] and c[1]["error"]
    assert server.search_controls("pinned")[0]["id"] == "ISM-2154"
    assert len(server.get_obligation()) >= 9
    assert server.get_essentials_action()["actions"] == 58
    assert server.diff_release()["changed"] == 146
    st = server.kb_status()
    assert st["counts"]["controls"] == 1143 and st["limits"] and st["levels"]


def test_bad_inputs_become_tool_errors(tmp_path):
    with pytest.raises(ToolError):
        server.review_project(path=str(tmp_path / "nope"), entity_type="non_corporate_commonwealth")
    with pytest.raises(ToolError):
        server.assess_applicability("non_corporate_commonwealth", classification="PURPLE")
    with pytest.raises(ToolError):
        server.get_obligation("X")


def test_roots_restrict_reads(tmp_path, monkeypatch):
    monkeypatch.setenv(server.ROOTS_ENV, str(tmp_path / "allowed"))
    (tmp_path / "allowed").mkdir()
    with pytest.raises(ToolError):
        server.review_project(path=str(tmp_path), entity_type="non_corporate_commonwealth")
    server.review_project(path=str(tmp_path / "allowed"), entity_type="non_corporate_commonwealth")


def test_authorisation_readiness(bad_repo, clean_repo):
    bad = server.authorisation_readiness(str(bad_repo), "non_corporate_commonwealth")
    assert not bad["ready_to_proceed_to_authorisation"] and any(p["if_missing"] for p in bad["preconditions"])
    assert server.authorisation_readiness(str(clean_repo), "non_corporate_commonwealth", phase="assess")["ready_to_proceed_to_authorisation"]


def test_http_requires_roots(monkeypatch):
    monkeypatch.delenv(server.ROOTS_ENV, raising=False)
    with pytest.raises(SystemExit):
        server.main(http=True)


def test_ids_are_case_insensitive():
    assert server.interrogate("r-pinned-deps")["controls"] == ["ISM-2154"]
    assert server.interrogate("pre-irp")["requirement"][0]["control"] == "ISM-0043"
    assert server.interrogate("pspf-14-strategy")["requirement_ref"] == "0098"
    ea = next(i for i, a in server._load().essentials.items() if a["ism"])
    assert server.interrogate(ea.lower())["id"] == ea and server.get_essentials_action(ea.lower())["id"] == ea
