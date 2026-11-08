import pytest

from ism_requirements_au import kb as K
from ism_requirements_au import profile as PR
from ism_requirements_au import review as RV


def run(path, **kw):
    args = dict(classification="PROTECTED", entity_type="non_corporate_commonwealth", hosting="unknown", phase="assess")
    return RV.build(K.load(), path, **{**args, **kw})


def test_levels_and_blockers(bad_repo):
    r = run(bad_repo)
    assert r["summary"]["by_level"]["blocker"] >= 4 and not r["readiness"]["ready_to_proceed_to_authorisation"]
    blockers = {f["rule"] for f in r["findings"] if f["level"] == "blocker"}
    assert {"PRE-IRP", "PRE-CMP", "R-MFA"} <= blockers  # MFA is an Essential Eight ML2 strategy, mandatory under PSPF section 14
    secret = next(f for f in r["findings"] if f["rule"] == "R-CRED-SHORT-LIVED")
    assert secret["urgent"] and secret["level"] == "gap"


def test_unread_precondition_is_info_not_missing(bad_repo):
    r = run(bad_repo)
    ssp = next(p for p in r["readiness"]["preconditions"] if p["id"] == "PRE-SSP")
    assert ssp["status"] == "found_unread"
    assert next(f for f in r["findings"] if f["rule"] == "PRE-SSP")["level"] == "info"


def test_phase_moves_findings_to_plan(bad_repo):
    early = run(bad_repo, phase="define")
    late = run(bad_repo, phase="assess")
    assert early["summary"]["by_level"]["blocker"] < late["summary"]["by_level"]["blocker"]
    assert next(f for f in early["findings"] if f["rule"] == "PRE-IRP")["level"] == "plan"


def test_clean_repo_ready(clean_repo):
    r = run(clean_repo)
    assert r["readiness"]["ready_to_proceed_to_authorisation"] and r["summary"]["by_level"]["blocker"] == 0
    assert r["summary"]["by_tier"]["rule"] == 0


def test_non_pspf_entity_gets_no_e8_blocker(bad_repo):
    r = run(bad_repo, entity_type="private_sector", supplies_government=False)
    assert not [f for f in r["findings"] if f["tier"] == "rule" and f["level"] == "blocker"]
    assert r["applicability"]["authorisation_required"] is False
    assert not [f for f in r["findings"] if f["tier"] == "precondition" and f["level"] == "blocker"]


def test_compact_is_small_and_pages(bad_repo):
    r = run(bad_repo)
    c = RV.compact(r, limit=2)
    assert all(len(v) <= 2 for v in c["findings"].values()) and c["more"]["gap"] > 0
    nxt = RV.compact(r, level="gap", limit=2, offset=2)
    assert nxt["findings"]["gap"][0]["id"] != c["findings"]["gap"][0]["id"]
    full = RV.compact(r, detail="full")
    assert len(str(c)) < len(str(full)) / 3


def test_since_returns_only_new_and_resolved(tmp_path):
    (tmp_path / "a.tf").write_text('mfa_configuration = "OFF"\n', encoding="utf-8")
    first = run(tmp_path)
    (tmp_path / "b.tf").write_text('acl = "public-read"\n', encoding="utf-8")
    (tmp_path / "a.tf").write_text('mfa_configuration = "ON"\n', encoding="utf-8")
    second = run(tmp_path)
    d = RV.compact(second, since=first["run_id"])["delta"]
    assert d["new"] and d["resolved"]
    with pytest.raises(ValueError):
        RV.compact(second, since="nope")


def test_applicability_rules():
    kb = K.load()
    a = PR.assess_applicability(kb, "non_corporate_commonwealth", "PROTECTED")
    assert a["pspf"]["binds"] == "yes" and a["e8_target"] == "ML2" and a["authorisation_required"]
    csp = PR.assess_applicability(kb, "private_sector", "PROTECTED", provides_cloud_service=True, apra_regulated=True, critical_infrastructure=True)
    assert csp["irap"]["required_for_this_system"] and csp["e8_target"] is None and {o["id"] for o in csp["sector_overlays"]} == {"CPS-234", "SOCI"}
    with pytest.raises(ValueError):
        PR.assess_applicability(kb, "martian")


def test_scope_system_counts_and_filters():
    kb = K.load()
    p = PR.scope_system(kb, "PROTECTED")
    ts = PR.scope_system(kb, "TOP SECRET")
    assert 0 < p["in_project_scope"] < p["applicable_controls"] and ts["applicable_controls"] != p["applicable_controls"]
    with_e8 = PR.scope_system(kb, "NON-CLASSIFIED", "ML2")
    assert with_e8["applicable_controls"] >= PR.scope_system(kb, "NON-CLASSIFIED")["applicable_controls"]
    one = PR.scope_system(kb, "PROTECTED", section="Software development fundamentals")
    assert one["sections"][0]["ids"] and "ISM-2154" in one["sections"][0]["ids"]
    assert "ids" not in p["sections"][0]


def test_essentials_domains_are_inferred_with_evidence(bad_repo):
    r = run(bad_repo)
    ds = {d["domain"]: d for d in r["essentials_domains"]["domains"]}
    assert "Identity services" in ds and ds["Identity services"]["evidence"] and r["essentials_domains"]["source"] == "inferred"
