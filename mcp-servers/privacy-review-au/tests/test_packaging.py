import re
from pathlib import Path

import privacy_review_au

ROOT = Path(__file__).resolve().parents[1]


def test_version_agrees():
    m = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    assert m and m.group(1) == privacy_review_au.__version__


def test_kb_is_package_data():
    assert (ROOT / "src/privacy_review_au/data/kb.json").exists()
