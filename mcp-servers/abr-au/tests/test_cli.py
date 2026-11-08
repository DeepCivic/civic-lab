import json
from pathlib import Path

import httpx
from conftest import ABN_CO, ALL_RECORDS, write_full_extract

from abr_au import cli
from abr_au.index import LocalIndex


def fake_data_gov(tmp_path: Path, last_modified: dict):
    zip_bytes = write_full_extract(tmp_path / "zipsrc", ALL_RECORDS, as_zip=True).read_bytes()
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if "package_show" in str(request.url):
            return httpx.Response(200, json={"result": {"resources": [
                {"url": "https://example.test/download/readme.pdf"},
                {"url": "https://example.test/download/public_split_1_20.zip",
                 "last_modified": last_modified["v"]},
            ]}})
        if request.url.path.endswith(".zip"):
            return httpx.Response(200, content=zip_bytes)
        return httpx.Response(404)

    return handler, requests


def test_update_index_builds_then_skips_then_rebuilds(tmp_path: Path, monkeypatch, capsys):
    stamp = {"v": "2026-11-03T21:34:04"}
    handler, requests = fake_data_gov(tmp_path, stamp)
    monkeypatch.setattr(cli, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    db = tmp_path / "data" / "abr.sqlite"

    assert cli.main(["update-index", "--db", str(db)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["complete"] and report["records"] == 4
    assert LocalIndex(db).get_by_abn(ABN_CO) is not None
    assert not list(db.parent.glob("abr-download-*")), "downloads are cleaned up"
    zip_gets = sum(p.endswith(".zip") for p in requests)

    # Same published extract: no download, no rebuild.
    assert cli.main(["update-index", "--db", str(db)]) == 0
    assert "nothing to do" in capsys.readouterr().err
    assert sum(p.endswith(".zip") for p in requests) == zip_gets

    # New extract published: rebuild.
    stamp["v"] = "2026-11-10T21:34:04"
    assert cli.main(["update-index", "--db", str(db)]) == 0
    assert sum(p.endswith(".zip") for p in requests) == zip_gets + 1
    assert "2026-11-10" in LocalIndex(db).meta()["source_stamp"]


def test_failed_download_reports_error_and_keeps_index(tmp_path: Path, monkeypatch, built_index: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "package_show" in str(request.url):
            return httpx.Response(200, json={"result": {"resources": [
                {"url": "https://example.test/x/public_split_1_10.zip", "last_modified": "new"}]}})
        return httpx.Response(500)

    monkeypatch.setattr(cli, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    before = built_index.read_bytes()
    assert cli.main(["update-index", "--db", str(built_index)]) == 1
    assert built_index.read_bytes() == before


def test_http_defaults_to_loopback(monkeypatch):
    from abr_au import server

    seen = {}
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.setattr(server.sys, "argv", ["abr-au", "--http"])
    if server._MCP_V2:
        monkeypatch.setattr(server.mcp, "run", lambda *a, **k: seen.update(k))
        server.main()
        assert seen["host"] == "127.0.0.1" and seen["stateless_http"] is True
    else:
        monkeypatch.setattr(server.mcp, "run", lambda *a, **k: seen.update(k))
        server.main()
        assert server.mcp.settings.host == "127.0.0.1"
