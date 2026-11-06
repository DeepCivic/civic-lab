"""Keep the distribution metadata consistent (PyPI, OCI, MCP Registry, MCPB)."""

import json
import re
from pathlib import Path

import abr_mcp

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    m = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    assert m
    return m.group(1)


def test_versions_agree():
    v = _pyproject_version()
    server = json.loads((ROOT / "server.json").read_text())
    manifest = json.loads((ROOT / "manifest.json").read_text())
    assert abr_mcp.__version__ == v == server["version"] == manifest["version"]
    for pkg in server["packages"]:
        if pkg["registryType"] == "pypi":
            assert pkg["version"] == v
        if pkg["registryType"] == "oci":
            assert pkg["identifier"].endswith(f":{v}")


def test_registry_name_is_verifiable():
    name = json.loads((ROOT / "server.json").read_text())["name"]
    assert f"mcp-name: {name}" in (ROOT / "README.md").read_text()  # PyPI ownership check
    assert f'io.modelcontextprotocol.server.name="{name}"' in (ROOT / "Dockerfile").read_text()


def test_manifest_tools_match_server():
    import asyncio

    from abr_mcp import server

    manifest = json.loads((ROOT / "manifest.json").read_text())
    listed = {t["name"] for t in manifest["tools"]}
    assert listed == {t.name for t in asyncio.run(server.mcp.list_tools())}
