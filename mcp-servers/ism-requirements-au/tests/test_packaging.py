import re
from pathlib import Path

import ism_requirements_au

ROOT = Path(__file__).resolve().parents[1]


def test_version_agrees():
    m = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    assert m and m.group(1) == ism_requirements_au.__version__
    assert f'"version": "{ism_requirements_au.__version__}"' in (ROOT / "server.json").read_text(encoding="utf-8")
    assert f"ism-requirements-au:{ism_requirements_au.__version__}" in (ROOT / "server.json").read_text(encoding="utf-8")


def test_kb_is_package_data():
    assert (ROOT / "src/ism_requirements_au/data/kb.json").exists()
