import json
import tomllib
from pathlib import Path

import pytest

import sanctions_au
from sanctions_au import cli, config, gleif_tools, server

PKG = Path(__file__).resolve().parent.parent


SCREENING = {"screen_subject", "screen_batch", "get_record", "dataset_status"}
GLEIF = {"lei_lookup", "validate_lei", "batch_lei_lookup", "search_entity", "search_by_bic", "search_by_isin",
         "search_by_country", "get_relationships", "autocomplete", "get_lei_issuer", "list_lei_issuers",
         "get_reporting_exceptions"}


@pytest.fixture
def offered(monkeypatch):
    """Build the server under a given configuration and return (tool names, instructions)."""
    import asyncio
    import importlib

    def load(**env):
        for name in (config.SCREENING_ENV, config.GLEIF_ENV):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        importlib.reload(gleif_tools)
        importlib.reload(server)
        listing = server.mcp.list_tools()
        tools = asyncio.run(listing) if asyncio.iscoroutine(listing) else listing
        return {t.name for t in tools}, server.INSTRUCTIONS

    yield load
    monkeypatch.undo()  # back to the default configuration for every later test
    importlib.reload(gleif_tools)
    importlib.reload(server)


def test_by_default_screening_is_offered_and_gleif_is_not(offered):
    names, instructions = offered()
    assert names == SCREENING
    assert "Screens people" in instructions and "GLEIF" not in instructions


def test_each_group_can_be_switched_on_and_off_independently(offered):
    assert offered(SANCTIONS_ENABLE_GLEIF="1")[0] == SCREENING | GLEIF
    names, instructions = offered(SANCTIONS_ENABLE_SCREENING="0", SANCTIONS_ENABLE_GLEIF="1")
    assert names == GLEIF and "Screens people" not in instructions and "GLEIF tools" in instructions
    names, instructions = offered(SANCTIONS_ENABLE_SCREENING="off")
    assert names == set() and "No tools are enabled" in instructions


def test_switching_both_off_says_so_on_stderr(offered, capsys):
    offered(SANCTIONS_ENABLE_SCREENING="no")
    assert "offers no tools" in capsys.readouterr().err


@pytest.mark.parametrize("value, expected", [("1", True), ("TRUE", True), (" Yes ", True), ("on", True),
                                              ("0", False), ("false", False), ("off", False), ("nonsense", False)])
def test_flags_use_the_sibling_servers_convention(monkeypatch, value, expected):
    monkeypatch.setenv(config.GLEIF_ENV, value)
    assert config.gleif_enabled() is expected


def test_flag_defaults(monkeypatch):
    monkeypatch.delenv(config.SCREENING_ENV, raising=False)
    monkeypatch.delenv(config.GLEIF_ENV, raising=False)
    monkeypatch.setenv(config.SCREENING_ENV, "")
    assert config.screening_enabled() is True and config.gleif_enabled() is False


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
