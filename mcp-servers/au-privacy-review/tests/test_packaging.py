import re
from pathlib import Path

import au_privacy_review

ROOT = Path(__file__).resolve().parents[1]


def test_version_agrees():
    m = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M)
    assert m and m.group(1) == au_privacy_review.__version__


def test_kb_is_package_data():
    assert (ROOT / "src/au_privacy_review/data/kb.json").exists()
