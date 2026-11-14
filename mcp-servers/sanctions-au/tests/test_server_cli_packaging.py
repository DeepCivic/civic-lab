import json
import tomllib
from pathlib import Path

import pytest

import sanctions_au
from sanctions_au import cli, server

PKG = Path(__file__).resolve().parent.parent


def test_tool_surface():
    import asyncio
    listing = server.mcp.list_tools()
    tools = asyncio.run(listing) if asyncio.iscoroutine(listing) else listing
    assert {t.name for t in tools} == {"screen_subject", "screen_batch", "get_record", "dataset_status"}


def test_tools_return_results_and_report_expected_failures(root):
    server._screener = None
    out = server.screen_subject(name="Kellan Dresdorf", date_of_birth="1971", country="Freedonia")
    assert out["overall"] == "potential_match" and out["dfat"]["matches"][0]["confidence"] == "high"
    assert out["dataset_versions"] and out["warnings"] and out["disclaimer"]
    batch = server.screen_batch(subjects=[server.Subject(ref="1", name="Kellan Dresdorf")], sources="dfat")
    assert batch["summary"] == {"subjects": 1, "potential_match": 1} and "abf" not in batch["results"][0]
    assert server.dataset_status()["datasets"]["dfat"]["available"]
    with pytest.raises(server.ToolError, match="YYYY-MM-DD"):
        server.screen_subject(name="Kellan Dresdorf", sanctioned_to="soon")
    with pytest.raises(server.ToolError, match="only stable"):
        server.get_record("abf", "nope")


def test_refresh_imports_files_and_a_bad_file_keeps_the_current_dataset(tmp_path, files, monkeypatch, capsys):
    monkeypatch.setenv("SANCTIONS_DATA_DIR", str(tmp_path / "d"))
    x, j = files
    assert cli.main(["refresh", "--dfat-file", str(x), "--abf-file", str(j)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dfat"]["outcome"] == report["abf"]["outcome"] == "new" and report["dfat"]["records"] == 4
    before = json.loads((tmp_path / "d" / "current" / "dfat.json").read_text())["snapshot_id"]
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"<html>blocked</html>")
    assert cli.main(["refresh", "--source", "dfat", "--dfat-file", str(bad)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["dfat"]["outcome"] == "failed" and "unchanged" in out["dfat"]["kept"]
    assert json.loads((tmp_path / "d" / "current" / "dfat.json").read_text())["snapshot_id"] == before
    assert cli.main(["status"]) == 0
    assert json.loads(capsys.readouterr().out)["datasets"]["dfat"]["available"]


def test_versions_agree_and_the_launch_script_exists():
    meta = tomllib.loads((PKG / "pyproject.toml").read_text())
    registry = json.loads((PKG / "server.json").read_text())
    assert meta["project"]["version"] == registry["version"] == sanctions_au.__version__
    assert registry["packages"][0]["identifier"].endswith(f":{sanctions_au.__version__}")
    assert meta["project"]["scripts"]["sanctions-au"] == "sanctions_au.cli:main"
