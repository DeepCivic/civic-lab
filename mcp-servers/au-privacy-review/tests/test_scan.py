import datetime as dt
import json
from pathlib import Path

from au_privacy_review import kb as _kb
from au_privacy_review.scan.scanner import scan_path

FIX = Path(__file__).parent / "fixtures"


def detectors(res):
    return {f["detector"] for f in res["findings"]}


def scan(path, **kw):
    return scan_path(_kb.load(), path, use_git=False, **kw)


def test_bad_fixture_signals():
    res = scan(FIX / "bad", min_severity="info")
    want = {"tracking-pixel", "session-replay", "biometric-processing", "weak-password-hashing", "tls-verification-disabled",
            "iac-public-storage", "mfa-disabled", "non-au-region", "government-identifier-as-key", "sensitive-fields-no-consent",
            "excessive-fields", "marketing-no-unsubscribe", "realistic-pii-in-fixtures", "consent-dark-patterns",
            "hedged-notice-language", "location-collection", "overseas-processor-sdk", "pii-in-logs", "automated-decision",
            "privacy-policy-omits-capability", "privacy-policy-contents", "no-pia", "hashed-identifier-sharing"}
    assert want <= detectors(res), want - detectors(res)


def test_sensitive_context_escalates_pixels():
    res = scan(FIX / "bad")
    px = [f for f in res["findings"] if f["detector"] == "tracking-pixel"]
    assert px and all(f["severity"] == "critical" for f in px)
    assert {"fertility", "telehealth"} & set(res["context"]["sensitive_context_terms"])
    # In a sensitive context the pixel engages APP 3.3 (Monash IVF / Medmate), so it is rule tier.
    assert all(f["tier"] == "rule" for f in px)


def test_pixel_without_sensitive_context_is_heuristic(tmp_path):
    (tmp_path / "README.md").write_text("# Garden widgets\nA shop for garden widgets.\n")
    (tmp_path / "index.html").write_text("<script>fbq('init', '1234');</script>\n")
    res = scan(tmp_path)
    px = [f for f in res["findings"] if f["detector"] == "tracking-pixel"]
    assert px and px[0]["tier"] == "heuristic" and px[0]["severity"] == "medium"
    assert "R-APP3.3-SENSITIVE-WITHOUT-CONSENT" not in {e["id"] for e in px[0]["kb"]}


def test_fixture_pii_links_tfn_rule_only_for_tfns(tmp_path):
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "people.json").write_text('[{"email": "someone@gmail.com"}]')
    res = scan(tmp_path)
    f = next(f for f in res["findings"] if f["detector"] == "realistic-pii-in-fixtures")
    assert "R-TFN-MISHANDLING" not in {e["id"] for e in f["kb"]} and f["tier"] == "heuristic"


def test_uuid_is_not_a_card_number(tmp_path):
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures" / "orgs.json").write_text('[{"id": "46fd8481-9bf1-4be7-b309-01798185123f"}]')
    assert "realistic-pii-in-fixtures" not in detectors(scan(tmp_path))


def test_build_output_and_minified_bundles_skipped(tmp_path):
    (tmp_path / ".vercel" / "output").mkdir(parents=True)
    (tmp_path / ".vercel" / "output" / "x.html").write_text("<script>fbq('init', '1');</script>")
    (tmp_path / "app.min.js").write_text("fbq('init','1');" + "x" * 6000)
    res = scan(tmp_path)
    assert "tracking-pixel" not in detectors(res)


def test_gitignore_honoured(tmp_path):
    import subprocess
    if subprocess.run(["git", "init", "-q", str(tmp_path)], capture_output=True).returncode != 0:
        return
    (tmp_path / ".gitignore").write_text("generated/\n")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "x.html").write_text("<script>fbq('init', '1');</script>")
    res = scan_path(_kb.load(), tmp_path)
    assert res["noise_control"]["gitignore_honoured"] and "tracking-pixel" not in detectors(res)


def test_diagnostics_is_not_a_health_field(tmp_path):
    (tmp_path / "lsp.ts").write_text("const diagnostics: Diagnostic[] = [];\nconst race = 1; // race condition guard\n")
    assert "sensitive-fields-no-consent" not in detectors(scan(tmp_path))


def test_data_json_is_not_iac(tmp_path):
    (tmp_path / "content.json").write_text(json.dumps({"articles": [{"body": 'acl = "public-read" and the disability support pension'}]}))
    res = scan(tmp_path)
    assert not {"iac-public-storage", "sensitive-fields-no-consent"} & detectors(res)


def test_line_suppression(tmp_path):
    (tmp_path / "a.py").write_text("requests.get(u, verify=False)  # privacy-review: ignore\nrequests.get(u, verify=False)\n")
    res = scan(tmp_path)
    tls = [f for f in res["findings"] if f["detector"] == "tls-verification-disabled"]
    assert len(tls) == 1 and tls[0]["line"] == 2


def test_duplicates_grouped(tmp_path):
    for d in ("static", "public"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "page.html").write_text("<script>\nfbq('init', '1');\nfbq('track', 'PageView');\n</script>")
    px = [f for f in scan(tmp_path)["findings"] if f["detector"] == "tracking-pixel"]
    assert len(px) == 1 and px[0]["occurrences"] == 4


def test_library_skips_absence_checks(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"name": "lib", "exports": {".": "./dist/index.js"}, "peerDependencies": {"svelte": "^5"}}))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "user.ts").write_text("export type User = { email: string; phone: string }\n")
    res = scan(tmp_path)
    assert res["context"]["system_kind"] == "library"
    assert not {"privacy-policy-missing", "no-retention-controls", "no-breach-runbook", "no-audit-logging"} & detectors(res)


def test_inventory(tmp_path):
    res = scan(FIX / "bad")
    inv = res["data_inventory"]
    assert inv["handles_personal_information"]
    assert {"contact", "sensitive", "government_identifier", "biometric"} <= set(inv["personal_information"])
    assert "diagnosis" in inv["personal_information"]["sensitive"]["fields"]
    names = {r["name"] for r in inv["recipients"]}
    assert {"OpenAI", "Meta Pixel", "Hotjar"} <= names
    assert "us-east-1" in inv["overseas"]["non_australian_regions"]
    assert any(c["file"] == "web/book.html" for c in inv["collection_points"])


def test_hosting_provider_recipient(tmp_path):
    (tmp_path / "vercel.json").write_text('{"regions": ["iad1"]}')
    r = next(r for r in scan(tmp_path)["data_inventory"]["recipients"] if r["name"] == "Vercel")
    assert r["overseas_likely"] is True
    (tmp_path / "vercel.json").write_text('{"regions": ["syd1"]}')
    r = next(r for r in scan(tmp_path)["data_inventory"]["recipients"] if r["name"] == "Vercel")
    assert r["overseas_likely"] is False


def test_future_obligation_marked():
    res = scan(FIX / "bad", as_at=dt.date(2026, 11, 7))
    adm = next(f for f in res["findings"] if f["detector"] == "automated-decision")
    assert adm["kb"][0]["not_yet_in_force"] is True


def test_findings_carry_citations():
    res = scan(FIX / "bad")
    for f in res["findings"]:
        assert f["kb"] and all(e["key_citations"] for e in f["kb"])


def test_clean_fixture_quiet():
    res = scan(FIX / "clean", min_severity="info")
    assert res["findings"] == [], [(f["detector"], f.get("file")) for f in res["findings"]]


def test_secrets_are_redacted(tmp_path):
    (tmp_path / "config.py").write_text('KEY = "AKIAABCDEFGHIJKLMNOP"\nDB = "postgres://admin:hunter2secret@db.prod.internal.net/app"\n')
    res = scan(tmp_path)
    ev = " ".join(f.get("evidence", "") for f in res["findings"])
    assert "hunter2secret" not in ev and "AKIAABCDEFGHIJKLMNOP" not in ev
    assert "hardcoded-secret" in detectors(res)


def test_secret_in_test_file_downgraded(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text('KEY = "AKIAABCDEFGHIJKLMNOP"\n')
    f = next(f for f in scan(tmp_path)["findings"] if f["detector"] == "hardcoded-secret")
    assert f["severity"] == "low"
