"""The documentation describes what the server does. Fail when they drift apart."""

import asyncio
import re
from pathlib import Path

from ism_requirements_au import server
from ism_requirements_au import track as T

ROOT = Path(__file__).resolve().parents[1]


def test_every_tool_is_documented():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for t in asyncio.run(server.mcp.list_tools()):
        assert f"`{t.name}`" in text, t.name


def test_every_prompt_is_documented():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for p in asyncio.run(server.mcp.list_prompts()):
        assert f"`{p.name}`" in text, p.name


def test_every_rule_is_documented():
    from ism_requirements_au import kb

    text = (ROOT / "docs" / "rules.md").read_text(encoding="utf-8")
    for r in kb.load().rules:
        assert f"`{r['id']}`" in text, r["id"]


def test_manifest_statuses_documented():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for s in T.STATUSES:
        assert s in text


def test_relative_links_resolve():
    for md in [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "RESEARCH.md", *(ROOT / "docs").glob("*.md")]:
        for target in re.findall(r"\]\((?!https?://|#)([^)#]+)", md.read_text(encoding="utf-8")):
            assert (md.parent / target).exists(), f"{md.name}: {target}"
