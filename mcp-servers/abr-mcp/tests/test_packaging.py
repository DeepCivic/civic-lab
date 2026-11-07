"""Keep the release metadata consistent (OCI image, MCP Registry)."""

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
    assert abr_mcp.__version__ == v == server["version"]
    for pkg in server["packages"]:
        assert pkg["registryType"] == "oci"  # image only: not published to PyPI
        assert pkg["identifier"].endswith(f":{v}")


def test_registry_name_is_verifiable():
    name = json.loads((ROOT / "server.json").read_text())["name"]
    assert f'io.modelcontextprotocol.server.name="{name}"' in (ROOT / "Dockerfile").read_text()
