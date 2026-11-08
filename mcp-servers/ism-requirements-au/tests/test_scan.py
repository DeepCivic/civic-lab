from ism_requirements_au.scan.scanner import scan_path


def by(res):
    out = {}
    for f in res["findings"]:
        out.setdefault(f["detector"], []).append(f)
    return out


def test_bad_repo_signals(bad_repo):
    d = by(scan_path(bad_repo))
    for det in ("static-cloud-key", "secret-literal", "default-credentials", "mfa-disabled", "tls-old-version", "open-ingress", "public-storage",
                "cookie-flags-off", "injection-sink", "unsafe-deserialisation", "unpinned-dependencies", "untrusted-source", "agent-broad-tools",
                "ci-no-security-testing", "no-sbom", "env-shared-secret", "no-security-headers"):
        assert det in d, det
    assert d["mfa-disabled"][0]["file"] == "infra/main.tf" and d["mfa-disabled"][0]["line"] == 13


def test_secrets_are_redacted_in_evidence(bad_repo):
    from conftest import AWS_KEY, DB_PASSWORD

    blob = str(scan_path(bad_repo)["findings"])
    assert AWS_KEY not in blob and DB_PASSWORD not in blob


def test_clean_repo_has_no_presence_findings(clean_repo):
    res = scan_path(clean_repo)
    assert [f for f in res["findings"] if f["kind"] == "presence"] == [], res["findings"]
    assert [f["detector"] for f in res["findings"]] == [], res["findings"]


def test_ignore_markers(tmp_path):
    (tmp_path / "a.tf").write_text('mfa_configuration = "OFF"  # ism-review: ignore\n', encoding="utf-8")
    (tmp_path / "b.tf").write_text('# ism-review: ignore-file\nmfa_configuration = "OFF"\n', encoding="utf-8")
    assert not [f for f in scan_path(tmp_path)["findings"] if f["detector"] == "mfa-disabled"]


def test_tls_12_is_not_flagged(tmp_path):
    (tmp_path / "n.conf").write_text("ssl_protocols TLSv1.2 TLSv1.3;\nmin_tls_version = \"TLS1_2\"\n", encoding="utf-8")
    assert not [f for f in scan_path(tmp_path)["findings"] if f["detector"] == "tls-old-version"]


def test_markers_collected(tmp_path):
    (tmp_path / "x.py").write_text("# ism: ISM-2154, ISM-0400\nx = 1\n", encoding="utf-8")
    assert {m["control"] for m in scan_path(tmp_path)["markers"]} == {"ISM-2154", "ISM-0400"}


def test_not_a_directory(tmp_path):
    import pytest

    with pytest.raises(ValueError):
        scan_path(tmp_path / "missing")


def test_bulk_json_and_mcp_servers_are_not_misread(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/kb.json").write_text('{"quote": "mfa_enabled: false was recorded"}\n', encoding="utf-8")
    (tmp_path / "server.py").write_text(
        'from mcp.server.fastmcp import FastMCP\nmcp = FastMCP("x")\n\n@mcp.tool()\ndef t(): ...\n'
        'def d(con, sub, ids):\n    con.execute(f"DELETE FROM n WHERE r IN ({sub})", (ids,))\n', encoding="utf-8")
    d = {f["detector"] for f in scan_path(tmp_path)["findings"]}
    assert not d & {"mfa-disabled", "agent-no-register", "injection-sink"}, d


def test_concatenated_sql_is_still_flagged(tmp_path):
    (tmp_path / "q.py").write_text('def q(cur, name):\n    cur.execute("SELECT * FROM t WHERE n = \'" + name + "\'")\n', encoding="utf-8")
    assert any(f["detector"] == "injection-sink" for f in scan_path(tmp_path)["findings"])
