"""The local index is optional, can be scoped to stay small, and can be built from the MCP tool."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from conftest import ABN_CHARITY, ABN_CO, ABN_IND, ABN_TRUST, ALL_RECORDS, write_full_extract
from test_cli import fake_data_gov
from test_service_and_web import jsonp, no_web, web_client

from abr_mcp import cli, jobs, updater
from abr_mcp.index import IndexScope, LocalIndex, build_index, estimate_index
from abr_mcp.service import AbrService


def build(tmp_path: Path, scope: IndexScope, name: str = "abr.sqlite") -> Path:
    src = write_full_extract(tmp_path / "extract", ALL_RECORDS)
    db = tmp_path / name
    build_index([src], db, scope=scope)
    return db


def test_scope_validation():
    assert IndexScope.make().full
    s = IndexScope.make(True, ["vic", " NSW "], ["bn", "MN"])
    assert s.states == ("NSW", "VIC") and s.name_types == ("BN", "MN") and not s.full
    assert IndexScope.from_meta(s.to_meta()) == s and IndexScope.from_meta("") == IndexScope()
    with pytest.raises(ValueError, match="state"):
        IndexScope.make(states=["Victoria"])
    with pytest.raises(ValueError, match="name type"):
        IndexScope.make(name_types=["XYZ"])


def test_estimates_shrink_with_scope():
    full = estimate_index(IndexScope())["bytes"]
    active = estimate_index(IndexScope.make(active_only=True))["bytes"]
    vic = estimate_index(IndexScope.make(active_only=True, states=["VIC"], name_types=["MN", "LGL", "BN"]), fts=False)["bytes"]
    assert 6.5e9 < full < 7.5e9  # matches the measured full build
    assert vic < 1e9 < active < full


def test_scoped_build_keeps_only_what_was_asked(tmp_path: Path):
    db = build(tmp_path, IndexScope.make(active_only=True, states=["VIC"], name_types=["MN"]))
    idx = LocalIndex(db)
    meta = idx.meta()
    assert meta["complete"] == "1"  # every file was still read and verified
    assert meta["record_count"] == "1" and meta["records_out_of_scope"] == "3"
    rec = idx.get_by_abn(ABN_CO)
    assert rec and [t for t, _ in rec["names"]] == ["MN"]  # BN and TRD dropped
    assert idx.get_by_abn(ABN_IND) is None and idx.get_by_abn(ABN_TRUST) is None


def test_scoped_miss_is_not_called_unregistered(tmp_path: Path):
    db = build(tmp_path, IndexScope.make(states=["VIC"]))
    out = AbrService(LocalIndex(db), no_web()).lookup_abn(ABN_IND, source="local")
    assert out["found"] is False and out["reason"] == "not_in_index_scope"
    assert "in VIC" in out["detail"] and "not registered" not in out["reason"]
    assert any("only part of the register" in c for c in out["caveats"])
    status = AbrService(LocalIndex(db), no_web()).status()["local_index"]
    assert status["scope"] == "active and cancelled ABNs in VIC"


def test_scoped_miss_falls_back_to_web(tmp_path: Path):
    db = build(tmp_path, IndexScope.make(states=["VIC"]))
    payload = {"Abn": ABN_IND, "AbnStatus": "Active", "EntityName": "CITIZEN, JANE", "AddressState": "NSW",
               "AddressPostcode": "2000", "EntityTypeCode": "IND", "EntityTypeName": "Individual/Sole Trader",
               "BusinessName": [], "Gst": None, "Message": ""}
    s = AbrService(LocalIndex(db), web_client(lambda r: jsonp(payload)))
    out = s.lookup_abn(ABN_IND)
    assert out["found"] and out["provenance"]["source"] == "abr_web_services"
    assert "which holds only" in out["local_index"]


def test_no_index_needed_with_a_guid():
    payload = {"Abn": ABN_CHARITY, "AbnStatus": "Active", "EntityName": "X", "AddressState": "QLD",
               "AddressPostcode": "4000", "EntityTypeCode": "CHT", "EntityTypeName": "Charitable Trust",
               "BusinessName": [], "Gst": None, "Message": ""}
    s = AbrService(LocalIndex("/nonexistent/abr.sqlite"), web_client(lambda r: jsonp(payload)))
    assert s.lookup_abn(ABN_CHARITY)["found"]
    assert s.status()["local_index"]["available"] is False


def test_cli_scope_flags_and_rebuild_on_scope_change(tmp_path: Path, monkeypatch, capsys):
    handler, requests = fake_data_gov(tmp_path, {"v": "2026-11-03"})
    monkeypatch.setattr(cli, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    db = tmp_path / "data" / "abr.sqlite"
    assert cli.main(["update-index", "--db", str(db), "--active-only"]) == 0
    assert json.loads(capsys.readouterr().out)["records"] == 3  # the cancelled trust is out of scope
    assert cli.main(["update-index", "--db", str(db), "--active-only"]) == 0
    assert "nothing to do" in capsys.readouterr().err
    assert cli.main(["update-index", "--db", str(db), "--active-only", "--state", "VIC"]) == 0  # new scope: rebuild
    assert json.loads(capsys.readouterr().out)["records"] == 1
    assert cli.main(["estimate", "--active-only", "--state", "VIC", "--no-fts"]) == 0
    assert json.loads(capsys.readouterr().out)["gb"] < 1


def test_build_job_from_local_files(tmp_path: Path):
    src = write_full_extract(tmp_path / "extract", ALL_RECORDS, as_zip=True).parent
    target = tmp_path / "idx" / "abr.sqlite"
    b = jobs.Builds()
    plan = b.plan(IndexScope.make(active_only=True), fts=True, source_dir=src, target=target)
    assert plan["source_dir"] == str(src) and "download_gb" not in plan and plan["estimated_index_gb"] > 0
    assert not target.exists()  # planning builds nothing
    b.start(IndexScope.make(active_only=True), fts=True, source_dir=src, force=False, target=target)
    b.wait(60)
    st = b.status()
    assert st["state"] == "done" and st["result"]["records"] == 3, st
    assert LocalIndex(target).get_by_abn(ABN_CO) is not None


def test_build_job_downloads(tmp_path: Path, monkeypatch):
    handler, _ = fake_data_gov(tmp_path, {"v": "2026-11-03"})
    monkeypatch.setattr(updater, "client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    target = tmp_path / "idx" / "abr.sqlite"
    b = jobs.Builds()
    assert "download_gb" in b.plan(IndexScope(), fts=True, source_dir=None, target=target)
    b.start(IndexScope(), fts=True, source_dir=None, force=False, target=target)
    b.wait(60)
    assert b.status()["state"] == "done" and LocalIndex(target).meta()["complete"] == "1"


def test_build_job_failure_is_reported(tmp_path: Path):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "x.xml").write_text("<nope/>")
    b = jobs.Builds()
    b.start(IndexScope(), fts=True, source_dir=bad, force=False, target=tmp_path / "abr.sqlite")
    b.wait(60)
    st = b.status()
    assert st["state"] == "failed" and "left in place" in st["note"]


def test_builds_disabled_over_http_unless_allowed(monkeypatch):
    monkeypatch.delenv(jobs.ALLOW_ENV, raising=False)
    assert jobs.allowed(http=False) and not jobs.allowed(http=True)
    monkeypatch.setenv(jobs.ALLOW_ENV, "1")
    assert jobs.allowed(http=True)
    monkeypatch.setenv(jobs.ALLOW_ENV, "0")
    assert not jobs.allowed(http=False)


def test_build_index_tool_plans_then_starts(tmp_path: Path, monkeypatch):
    from abr_mcp import server

    src = write_full_extract(tmp_path / "extract", ALL_RECORDS)
    target = tmp_path / "idx" / "abr.sqlite"
    monkeypatch.setattr(server, "_service", AbrService(LocalIndex(target), no_web()))
    monkeypatch.setattr(server, "_builds", jobs.Builds())
    monkeypatch.setattr(server, "_HTTP", False)
    plan = server.build_index(states=["VIC"], source_dir=str(src))
    assert "plan" in plan and not target.exists()
    started = server.build_index(states=["VIC"], source_dir=str(src), start=True)
    assert started["started"]
    server._builds.wait(60)
    status = server.register_status()
    assert status["index_build"]["state"] == "done" and status["local_index"]["scope"] == "active and cancelled ABNs in VIC"
    monkeypatch.setattr(server, "_HTTP", True)
    monkeypatch.delenv(jobs.ALLOW_ENV, raising=False)
    with pytest.raises(Exception, match="disabled"):
        asyncio.run(server.mcp.call_tool("build_index", {}))
