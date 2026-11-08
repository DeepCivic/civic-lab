"""Deterministic control tracking. The server never writes: it returns content or patches for the agent to write, and
`verify` checks a manifest offline (no network, no model; the same inputs give the same exit code)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from .kb import E8_LEVELS, KB, classification_tag

STATUSES = ["implemented", "partial", "planned", "not_applicable", "risk_accepted"]
FIDELITIES = ["direct", "partial", "supporting"]
MECHANISMS = ["ci", "iac", "code", "config", "document", "process", "platform", "inherited"]
DEFAULT_MANIFEST = ".ism/controls.yaml"
RESPONSIBILITY = ["Not Determined", "Board / Executive Committee", "Chief Information Security Officer", "System Owner", "Internal Service Provider",
                  "External Service Provider", "Consumer", "Shared", "Not Applicable"]
SOURCE = ["Not Determined", "Self-Implemented", "Inherited", "Hybrid", "Not Applicable"]


def text_sha256(statement: str) -> str:
    return hashlib.sha256(statement.encode("utf-8")).hexdigest()


def parse(text: str) -> dict:
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"manifest is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("manifest must be a YAML mapping with 'ism_release', 'scope' and 'controls'")
    if data.get("controls") is None:
        data["controls"] = []
    if not isinstance(data["controls"], list):
        raise ValueError("'controls' must be a list")
    for i, c in enumerate(data["controls"]):
        if not isinstance(c, dict):
            raise ValueError(f"controls[{i}] must be a mapping with at least 'id' (got {c!r:.60}); track_entry returns a valid entry")
    if data.get("scope") is not None and not isinstance(data["scope"], dict):
        raise ValueError("'scope' must be a mapping, e.g. {classification: PROTECTED, e8_target: ML2}")
    return data


def dump(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120)


def _entry(kb: KB, cid: str, status: str = "planned", phase: str | None = None) -> dict:
    c = kb.control(cid)
    rules = kb.rules_for_control(cid)
    e = {"id": c["id"], "text_sha256": text_sha256(c["statement"]), "essentials": c["essentials"], "phase": phase or (kb.entry(rules[0])["phase"] if rules else "implement"),
         "status": status, "fidelity": "supporting", "mechanism": {"kind": "process", "ref": ""}, "evidence": [], "reviewed_against": kb.release}
    return e


def plan(kb: KB, classification: str, e8_target: str | None = None, domains: list[str] | None = None, domains_source: str = "user",
         sections: list[str] | None = None, include_rules: bool = True) -> dict:
    """A starting manifest: the controls the rule set can help evidence, plus the preconditions' controls and any named sections."""
    tag = classification_tag(classification)
    ids: list[str] = []
    if include_rules:
        for p in kb.preconditions:
            ids += p["controls"]
        for r in kb.rules + kb.heuristics:
            ids += r["controls"]
    for c in kb.controls():
        if sections and any(s.lower() in c["section"].lower() or s.lower() in c["guideline"].lower() for s in sections):
            ids.append(c["id"])
    keep = []
    for i in dict.fromkeys(ids):
        c = kb.control(i)
        if kb.applies(c, tag, e8_target):
            keep.append(i)
    manifest = {"ism_release": kb.release, "scope": {"classification": classification, "pspf": bool(e8_target), "e8_target": e8_target or "none",
                                                      "essentials_domains": domains or [], "essentials_domains_source": domains_source},
                "controls": [_entry(kb, i) for i in keep]}
    return {"path": DEFAULT_MANIFEST, "controls": len(keep), "yaml": dump(manifest),
            "write": f"Write the YAML to {DEFAULT_MANIFEST}. Statuses start as 'planned'; change one only when you can name the mechanism and evidence.",
            "scope_note": "Add other controls with track_entry as the team takes them on."}


def entry(kb: KB, control_id: str, status: str, mechanism_kind: str = "process", mechanism_ref: str = "", evidence: list[str] | None = None,
          fidelity: str = "supporting", phase: str | None = None, responsibility: str | None = None, source: str | None = None, note: str | None = None) -> dict:
    cid = control_id.upper()
    if not kb.has_control(cid):
        raise ValueError(f"unknown control {control_id!r} in ISM {kb.release}")
    for val, allowed, name in ((status, STATUSES, "status"), (fidelity, FIDELITIES, "fidelity"), (mechanism_kind, MECHANISMS, "mechanism_kind")):
        if val not in allowed:
            raise ValueError(f"{name} must be one of {allowed}")
    if responsibility and responsibility not in RESPONSIBILITY:
        raise ValueError(f"responsibility must be one of {RESPONSIBILITY}")
    if source and source not in SOURCE:
        raise ValueError(f"source must be one of {SOURCE}")
    if phase and phase not in kb.phases:
        raise ValueError(f"phase must be one of {kb.phases}")
    problems = []
    if fidelity == "direct" and not mechanism_ref:
        problems.append("a 'direct' mapping needs a mechanism reference (a CI job, IaC resource, code path or config file) that enforces the control")
    if status == "implemented" and not (evidence or mechanism_ref):
        problems.append("'implemented' needs evidence or a mechanism")
    e = _entry(kb, cid, status, phase)
    e.update({"fidelity": fidelity, "mechanism": {"kind": mechanism_kind, "ref": mechanism_ref}, "evidence": list(evidence or [])})
    if responsibility:
        e["responsibility"] = responsibility
    if source:
        e["source"] = source
    if note:
        e["note"] = note
    return {"yaml": dump({"controls": [e]}).replace("controls:\n", "", 1), "append_under": "controls:", "warnings": problems,
            "statement": kb.control(cid)["statement"][:300]}


def gaps(kb: KB, manifest: dict, classification: str | None = None, e8_target: str | None = None, limit: int = 40) -> dict:
    scope = manifest.get("scope") or {}
    cl = classification or scope.get("classification")
    if not cl:
        raise ValueError("classification is not in the manifest scope; pass classification")
    tag = classification_tag(cl)
    e8t = e8_target or (scope.get("e8_target") if scope.get("e8_target") in E8_LEVELS else None)
    have = {c.get("id", "").upper(): c for c in manifest["controls"]}
    out = {"undeclared_rule_controls": [], "weak_entries": [], "applicable_not_declared": 0}
    rule_ids = []
    for r in kb.rules:
        rule_ids += r["controls"]
    for cid in dict.fromkeys(rule_ids):
        if kb.applies(kb.control(cid), tag, e8t) and cid not in have:
            out["undeclared_rule_controls"].append({"id": cid, "rules": kb.rules_for_control(cid)})
    for cid, c in have.items():
        if not kb.has_control(cid):
            continue
        why = []
        if c.get("status") == "implemented" and not (c.get("evidence") or (c.get("mechanism") or {}).get("ref")):
            why.append("implemented without evidence or mechanism")
        if c.get("fidelity") == "direct" and not (c.get("mechanism") or {}).get("ref"):
            why.append("direct without mechanism")
        if c.get("status") in ("planned", "partial"):
            why.append(f"status {c['status']}")
        if why:
            out["weak_entries"].append({"id": cid, "why": why})
    out["applicable_not_declared"] = sum(1 for c in kb.controls() if kb.applies(c, tag, e8t) and c["id"] not in have)
    out["undeclared_rule_controls"] = out["undeclared_rule_controls"][:limit]
    out["weak_entries"] = out["weak_entries"][:limit]
    out["note"] = "applicable_not_declared counts every applicable control without an entry; most are organisational and need no repository entry. verify --strict fails on them."
    return out


def impact(kb: KB, manifest: dict) -> dict:
    changed, unknown = [], []
    for c in manifest["controls"]:
        cid = str(c.get("id", "")).upper()
        k = kb.control(cid)
        if not k:
            unknown.append(cid)
            continue
        reasons = []
        if c.get("text_sha256") and c["text_sha256"] != text_sha256(k["statement"]):
            reasons.append("statement text differs from the pinned release")
        if c.get("reviewed_against") and c["reviewed_against"] != kb.release and k.get("updated"):
            reasons.append(f"reviewed against {c['reviewed_against']}; control updated {k['updated']} (revision {k['revision']})")
        if reasons:
            changed.append({"id": cid, "reasons": reasons, "updated": k.get("updated"), "revision": k.get("revision")})
    return {"manifest_release": manifest.get("ism_release"), "kb_release": kb.release, "changed": changed, "unknown_ids": unknown,
            "action": "Re-read each changed control with get_control, confirm the mechanism still satisfies it, then update text_sha256 and reviewed_against." if changed else "No pinned entries are affected."}


def ci_workflow() -> dict:
    wf = """name: ISM controls
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: Verify the ISM control manifest
        run: uvx --from "git+https://github.com/DeepCivic/civic-lab#subdirectory=mcp-servers/ism-requirements-au" ism-requirements-au verify --manifest .ism/controls.yaml
"""
    return {"path": ".github/workflows/ism-controls.yml", "yaml": wf,
            "notes": ["Add --strict to fail when an applicable rule-linked control has no manifest entry.",
                      "Pin the tool version once you adopt it (git+https://github.com/DeepCivic/civic-lab@ism-requirements-au-vX.Y.Z#subdirectory=...), "
                      "so the check does not change under you.",
                      "The package is not on PyPI. Once an image is released, this also works: "
                      "docker run --rm -v \"$PWD\":/work:ro ghcr.io/deepcivic/ism-requirements-au verify /work"]}


_MARKER = re.compile(r"\bism:\s*((?:ISM-\d{4}\s*,?\s*)+)", re.I)


def verify(kb: KB, root: Path, manifest_path: Path | None = None, strict: bool = False) -> dict:
    """Offline checks. Returns {ok, errors, warnings}. Same inputs, same result."""
    root = Path(root)
    mp = manifest_path or root / DEFAULT_MANIFEST
    errors: list[str] = []
    warnings: list[str] = []
    if not mp.is_file():
        return {"ok": False, "errors": [f"manifest not found: {mp}"], "warnings": [], "controls": 0}
    try:
        m = parse(mp.read_text(encoding="utf-8"))
    except ValueError as exc:
        return {"ok": False, "errors": [str(exc)], "warnings": [], "controls": 0}
    if m.get("ism_release") != kb.release:
        warnings.append(f"manifest pins ISM {m.get('ism_release')!r}; this tool carries {kb.release}. Run track_impact.")
    scope = m.get("scope") or {}
    tag = None
    try:
        tag = classification_tag(str(scope.get("classification", "")))
    except ValueError as exc:
        errors.append(f"scope.classification: {exc}")
    e8t = scope.get("e8_target") if scope.get("e8_target") in E8_LEVELS else None
    seen: set[str] = set()
    for i, c in enumerate(m["controls"]):
        cid = str(c.get("id", "")).upper()
        where = f"controls[{i}] {cid or '(no id)'}"
        if cid in seen:
            errors.append(f"{where}: duplicate entry")
        seen.add(cid)
        k = kb.control(cid)
        if not k:
            errors.append(f"{where}: not a control in ISM {kb.release}")
            continue
        if c.get("text_sha256") != text_sha256(k["statement"]):
            errors.append(f"{where}: text_sha256 does not match the control statement (reworded or mistyped); run track_impact")
        st = c.get("status")
        if st not in STATUSES:
            errors.append(f"{where}: status must be one of {STATUSES}")
        if c.get("fidelity") not in FIDELITIES:
            errors.append(f"{where}: fidelity must be one of {FIDELITIES}")
        if c.get("phase") is not None and c["phase"] not in kb.phases:
            errors.append(f"{where}: phase must be one of {kb.phases}")
        mech = c.get("mechanism") or {}
        if mech.get("kind") is not None and mech["kind"] not in MECHANISMS:
            errors.append(f"{where}: mechanism.kind must be one of {MECHANISMS}")
        if c.get("fidelity") == "direct" and not mech.get("ref"):
            errors.append(f"{where}: claims 'direct' without a mechanism reference")
        if st == "implemented" and not (c.get("evidence") or mech.get("ref")):
            errors.append(f"{where}: 'implemented' without evidence or mechanism")
        paths = list(c.get("evidence") or []) + ([mech["ref"]] if mech.get("ref") and mech.get("kind") in ("ci", "iac", "code", "config", "document") else [])
        for p in paths:
            if re.match(r"^[a-z][a-z0-9+.-]*://", str(p)):
                continue
            target = (root / str(p).split("#", 1)[0]).resolve()
            if root.resolve() not in (target, *target.parents):
                errors.append(f"{where}: evidence path escapes the project: {p}")
            elif not target.exists():
                errors.append(f"{where}: evidence path does not exist: {p}")
        if tag and st == "not_applicable" and kb.applies(k, tag, e8t) and not c.get("note"):
            warnings.append(f"{where}: marked not_applicable at {scope.get('classification')} without a note explaining why")
    # markers
    from .scan.files import walk  # local import: keeps verify light for callers that never scan

    w = walk(root)
    for f in w.files:
        if f.rel.replace("\\", "/") == str(mp.relative_to(root)).replace("\\", "/") if mp.is_relative_to(root) else False:
            continue
        for i, ln in enumerate(f.lines):
            mk = _MARKER.search(ln)
            if mk and "ism-review" not in ln:
                for cid in re.findall(r"ISM-\d{4}", mk.group(1), re.I):
                    cid = cid.upper()
                    if not kb.has_control(cid):
                        errors.append(f"{f.rel}:{i + 1}: marker names {cid}, which is not in ISM {kb.release}")
                    elif cid not in seen:
                        errors.append(f"{f.rel}:{i + 1}: marker names {cid}, which has no manifest entry")
    if strict and tag:
        have = {str(c.get("id", "")).upper() for c in m["controls"]}
        for r in kb.rules:
            for cid in r["controls"]:
                if cid not in have and kb.applies(kb.control(cid), tag, e8t):
                    errors.append(f"strict: applicable control {cid} (rule {r['id']}) has no manifest entry")
    errors = list(dict.fromkeys(errors))
    return {"ok": not errors, "errors": errors, "warnings": warnings, "controls": len(m["controls"]), "release": kb.release}
