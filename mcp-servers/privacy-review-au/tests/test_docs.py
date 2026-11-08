"""The documentation describes what the code does. Fail when they drift apart."""

import json
import re
from pathlib import Path

import privacy_review_au
from privacy_review_au import observations as O
from privacy_review_au import precedents as P
from privacy_review_au import threshold as T

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def test_every_observation_kind_is_documented():
    text = (DOCS / "using-the-review.md").read_text(encoding="utf-8")
    for k in O.KINDS:
        assert f"`{k.id}`" in text, k.id


def test_every_precedent_pattern_is_documented():
    text = (DOCS / "findings-reference.md").read_text(encoding="utf-8")
    for p in P.PATTERNS:
        assert f"`{p.id}`" in text, p.id


def test_every_threshold_question_is_documented():
    text = (DOCS / "threshold-assessment.md").read_text(encoding="utf-8")
    for q in T.QUESTIONS:
        assert f"`{q.id}`" in text, q.id
    assert f"{len(T.QUESTIONS)} questions" in text


def test_relative_links_resolve():
    for md in [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "RESEARCH.md", *DOCS.glob("*.md")]:
        for target in re.findall(r"\]\((?!https?://|#)([^)#]+)", md.read_text(encoding="utf-8")):
            assert (md.parent / target).exists(), f"{md.name}: {target}"


def test_registry_entry_matches_package():
    v = privacy_review_au.__version__
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["version"] == v
    assert all(p["identifier"].endswith(":" + v) for p in server["packages"] if p["registryType"] == "oci")
    assert not any(p["registryType"] == "pypi" for p in server["packages"])  # not published to PyPI
    assert f'io.modelcontextprotocol.server.name="{server["name"]}"' in (ROOT / "Dockerfile").read_text(encoding="utf-8")
