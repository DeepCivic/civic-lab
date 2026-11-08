import asyncio
from pathlib import Path

import pytest

from privacy_review_au import server
from privacy_review_au.server import ToolError
from privacy_review_au.scan import live


def test_tools_listed():
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert {"review_project", "interrogate", "list_observation_kinds", "threshold_assessment", "list_threshold_questions",
            "scan_repository", "get_entry", "get_app", "assess_applicability", "probe_deployment", "kb_status"} <= names


def test_review_tool_filters_and_threshold_shares_evidence():
    bad = str(Path(__file__).parent / "fixtures" / "bad")
    r = server.review_project(path=bad, min_level="high", include_report=False)
    assert r["findings"] and all(f["level"] in ("high", "critical") for f in r["findings"]) and "report_markdown" not in r
    assert r["summary"]["by_level"]["caution"] > 0  # the summary still counts everything
    t = server.threshold_assessment(path=bad)
    assert t["review_summary"]["by_level"] == r["summary"]["by_level"]
    assert any(i.get("precedent") for i in t["issues_for_pia"])
    with pytest.raises(ToolError):
        server.review_project(observations=[{"kind": "nope", "fact": "x"}])
    q = {x["id"]: x for x in server.list_threshold_questions()}
    assert q["large_scale"]["what_would_resolve"] and "large_scale" in q["large_scale"]["record_as"]


def test_get_entry_and_app():
    e = server.get_entry("R-APP11-PUBLIC-STORAGE")
    assert e["citations"][0]["citation"] == "Privacy Act 1988 (Cth)"
    assert "11.1" in server.get_app(11)["text"]


def test_applicability():
    small = server.assess_applicability("company", annual_turnover_aud=500_000)
    assert small["likely_app_entity"] is False and small["tort_exposure"] is True
    health = server.assess_applicability("company", annual_turnover_aud=500_000, provides_health_service=True)
    assert health["likely_app_entity"] is True
    assert any(c["pinpoint"] == "s 6D(4)(b)" for c in health["citations"])


def test_live_probe_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PRIVACY_REVIEW_AU_LIVE", raising=False)
    with pytest.raises(live.LiveDisabled):
        live.probe("https://example.com")


def test_search():
    hits = server.search_kb("tracking pixel")
    assert hits and hits[0]["id"] in {"H-TRACKING-PIXEL-SENSITIVE", "R-APP3.3-SENSITIVE-WITHOUT-CONSENT"}


def test_threshold_tool(tmp_path):
    r = server.threshold_assessment(answers={"handles_personal_information": False})
    assert r["outcome"] == "pia_not_indicated" and r["report_markdown"].startswith("# Privacy threshold assessment")
    assert len(server.list_threshold_questions()) == 17


def test_roots_restrict_paths(tmp_path, monkeypatch):
    inside = tmp_path / "ok"
    inside.mkdir()
    monkeypatch.setenv(server.ROOTS_ENV, str(inside))
    assert server.check_path(str(inside)) == inside.resolve()
    with pytest.raises(PermissionError):
        server.check_path(str(tmp_path))
    with pytest.raises(PermissionError):
        server.check_path(str(inside / ".." / ".."))


def test_http_requires_roots(monkeypatch):
    monkeypatch.delenv(server.ROOTS_ENV, raising=False)
    with pytest.raises(SystemExit):
        server.main(http=True)


def test_state_body_flags_state_law():
    r = server.assess_applicability("state_or_territory_body")
    assert r["likely_app_entity"] is False and any("not assessed" in x for x in r["reasons"])


def test_applicability_digital_id_layer():
    r = server.assess_applicability("company", annual_turnover_aud=1_000_000, digital_id_role="accredited_entity")
    assert r["likely_app_entity"] is False and r["digital_id"]["applies"]
    assert {c["pinpoint"] for c in r["digital_id"]["citations"]} == {"s 35", "s 28(2)(b)"}
    assert "digital_id" not in server.assess_applicability("company", annual_turnover_aud=5_000_000)
