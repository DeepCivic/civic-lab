import json

import pytest

from ism_requirements_au import cli


def run(args, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(args)
    return e.value.code, capsys.readouterr().out


def test_review_exit_codes(bad_repo, clean_repo, capsys):
    code, out = run(["review", str(bad_repo), "--entity-type", "non_corporate_commonwealth", "--phase", "assess"], capsys)
    assert code == 1 and "BLOCKER" in out
    code, _ = run(["review", str(bad_repo), "--entity-type", "non_corporate_commonwealth", "--fail-on", "never"], capsys)
    assert code == 0
    code, out = run(["review", str(clean_repo), "--entity-type", "non_corporate_commonwealth", "--phase", "assess", "--json"], capsys)
    assert code == 0 and json.loads(out)["readiness"]["blockers"] == 0


def test_verify_cli(clean_repo, tmp_path, capsys):
    import shutil

    proj = tmp_path / "p"
    shutil.copytree(clean_repo, proj)
    code, out = run(["verify", str(proj)], capsys)
    assert code == 1 and "manifest not found" in out
    (proj / ".ism").mkdir()
    (proj / ".ism/controls.yaml").write_text("ism_release: '2026.09'\nscope: {classification: PROTECTED}\ncontrols: []\n", encoding="utf-8")
    code, out = run(["verify", str(proj)], capsys)
    assert code == 0 and "ok" in out


def test_status(capsys):
    cli.main(["status"])
    assert json.loads(capsys.readouterr().out)["ism_release"] == "2026.09"
