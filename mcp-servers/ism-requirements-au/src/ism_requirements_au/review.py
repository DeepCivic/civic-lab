"""Join scanner signals to the knowledge base and rank them: blocker, gap, plan, info."""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path

from . import profile as PR
from .kb import E8_LEVELS, KB
from .scan import detectors as D
from .scan.scanner import scan_path

LEVELS = ["info", "plan", "gap", "blocker"]
LEVEL_MEANING = {
    "blocker": "Authorisation cannot proceed on current evidence: a precondition is missing, or a rule in a mandatory obligation reads as not met.",
    "gap": "A control in scope reads as unmet or unevidenced; the questions say what would settle it.",
    "plan": "In scope but belongs to a later step of the lifecycle; recorded so it is not forgotten.",
    "info": "Recorded for completeness (for example, not applicable at this classification, or a document found but not read).",
}
URGENT_RULES = {"R-CRED-SHORT-LIVED", "R-CRED-SECRETS-MANAGER", "R-CRED-CLEAR", "R-DEFAULT-CREDS"}

_RUNS: OrderedDict[str, dict] = OrderedDict()


def remember(run_id: str, findings: list[dict]) -> None:
    _RUNS[run_id] = {"ids": {f["id"] for f in findings}, "findings": {f["id"]: f for f in findings}}
    while len(_RUNS) > 20:
        _RUNS.popitem(last=False)


def recall(run_id: str) -> dict | None:
    return _RUNS.get(run_id)


def find_finding(fid: str) -> dict | None:
    for run in reversed(_RUNS.values()):
        if fid in run["findings"]:
            return run["findings"][fid]
    return None


def _trigger_ok(h: dict, ctx: dict, hosting: str) -> bool:
    t = h["trigger"]
    return (t == "always" or (t == "ai" and (ctx["ai"] or ctx["agents"])) or (t == "web" and ctx["web"])
            or (t == "cloud" and (ctx["cloud"] or hosting in ("cloud_csp", "hybrid"))) or (t == "online" and ctx["web"]))


def build(kb: KB, path: Path, *, classification: str, entity_type: str, hosting: str, phase: str, provides_cloud_service: bool = False,
          provides_gateway: bool = False, supplies_government: bool = True, apra_regulated: bool = False, critical_infrastructure: bool = False,
          exclude: list[str] | None = None, max_files: int = 20000) -> dict:
    if phase not in kb.phases:
        raise ValueError(f"phase must be one of {kb.phases}")
    appl = PR.assess_applicability(kb, entity_type, classification, hosting, provides_cloud_service, provides_gateway, supplies_government,
                                   apra_regulated, critical_infrastructure)
    tag, e8t = appl["classification_tag"], appl["e8_target"]
    cur = kb.phases.index(phase)
    s = scan_path(path, exclude=exclude, max_files=max_files)
    ctx, w = s["context"], s["walk"]
    out: list[dict] = []

    def applies(ids: list[str]) -> bool:
        return any(kb.applies(kb.control(i), tag, e8t) for i in ids)

    def mandatory_e8(ids: list[str]) -> str | None:
        if not e8t or appl["pspf"]["binds"] != "yes":
            return None
        lv = [kb.e8_min(i) for i in ids if kb.e8_min(i)]
        ok = [x for x in lv if E8_LEVELS.index(x) <= E8_LEVELS.index(e8t)]
        return min(ok, key=E8_LEVELS.index) if ok else None

    for g in s["findings"]:
        r = kb.entry(g["rule"])
        if r is None:
            continue
        ids = r["controls"]
        e8 = mandatory_e8(ids)
        later = kb.phases.index(r["phase"]) > cur
        if not applies(ids):
            level = "info"
        elif g["kind"] == "absence" and later:
            level = "plan"
        elif g["confidence"] == "high" and g["kind"] == "presence" and e8:
            level = "blocker"
        elif later and g["kind"] == "absence":
            level = "plan"
        else:
            level = "gap"
        f = {"id": "F-" + g["fingerprint"], "level": level, "tier": "rule", "rule": r["id"], "title": r["title"],
             "controls": ids, "fidelity": r["fidelity"], "confidence": g["confidence"], "kind": g["kind"], "phase": r["phase"],
             "message": g["message"], "settle": r["remediation"], "detector": g["detector"]}
        for k in ("file", "line", "evidence", "occurrences", "lines", "also_at"):
            if k in g:
                f[k] = g[k]
        if e8:
            f["e8_level"] = e8
        if r.get("e8_strategy"):
            f["e8_strategy"] = r["e8_strategy"]
        if r["essentials"]:
            f["essentials"] = r["essentials"]
        if r["id"] in URGENT_RULES and g["confidence"] == "high" and g["kind"] == "presence":
            f["urgent"] = True
        out.append(f)
    # one finding per fingerprint+rule (ids must be unique even when two rules share a fingerprint)
    seen: dict[str, int] = {}
    for f in out:
        n = seen.get(f["id"], 0)
        seen[f["id"]] = n + 1
        if n:
            f["id"] += f"-{n + 1}"

    # authorisation preconditions
    pre_status = D.precondition_status(kb.preconditions, w.files, w.all_paths, w.unread_documents)
    pre_rows = []
    csp_or_gw = provides_cloud_service or provides_gateway or hosting == "gateway"
    for p, st in zip(kb.preconditions, pre_status, strict=True):
        applicable = (p["applies"] == "authorisation" and appl["authorisation_required"]) or (p["applies"] == "pspf" and appl["pspf"]["binds"] in ("yes", "confirm")) or (p["applies"] == "csp_or_gateway" and csp_or_gw)
        status = "not_applicable" if not applicable else ("found_unread" if st["found"] and set(st["found"]) <= set(st["unread"]) else "found" if st["found"] else "not_found")
        pre_rows.append({"id": p["id"], "title": p["title"], "status": status, "found": st["found"], "phase": p["phase"], "controls": p["controls"]})
        if status == "not_found":
            due = kb.phases.index(p["phase"]) <= cur
            out.append({"id": "F-" + hashlib.sha1(p["id"].encode()).hexdigest()[:8], "level": "blocker" if due else "plan", "tier": "precondition", "rule": p["id"],
                        "title": p["title"] + " not found", "controls": p["controls"], "fidelity": "direct", "confidence": "medium", "kind": "absence", "phase": p["phase"],
                        "message": p["missing"] + " Searched file names and headings in the repository and any documents given; it may be held elsewhere.",
                        "settle": "Point to the document (path or link) or have it written; keep it in the repository or record where it lives."})
        elif status == "found_unread":
            out.append({"id": "F-" + hashlib.sha1((p["id"] + "u").encode()).hexdigest()[:8], "level": "info", "tier": "precondition", "rule": p["id"],
                        "title": p["title"] + " found by file name", "controls": p["controls"], "fidelity": "direct", "confidence": "medium", "kind": "presence",
                        "phase": p["phase"], "message": f"{', '.join(st['found'][:3])} looks like the {p['title'].lower()} but is a format this server does not read. Confirm its content.",
                        "settle": "Read the document and confirm it covers what the control requires."})

    # heuristics
    questions = []
    for h in kb.heuristics:
        if not _trigger_ok(h, ctx, hosting) or not applies(h["controls"]):
            continue
        later = kb.phases.index(h["phase"]) > cur
        out.append({"id": "F-" + hashlib.sha1(h["id"].encode()).hexdigest()[:8], "level": "plan" if later else "gap", "tier": "heuristic", "rule": h["id"], "title": h["title"],
                    "controls": h["controls"], "fidelity": "supporting", "confidence": h["confidence"], "kind": "question", "phase": h["phase"],
                    "message": h["concern"], "questions": h["questions"], "settle": "Evidence: " + h["evidence"]})
        questions.append({"id": h["id"], "title": h["title"], "questions": h["questions"], "evidence": h["evidence"]})

    rank = lambda f: (-LEVELS.index(f["level"]), not f.get("urgent"), f["tier"] != "precondition", f["tier"] == "heuristic", -D.CONFIDENCES.index(f["confidence"]), f["id"])  # noqa: E731
    out.sort(key=rank)

    # markers
    markers = s["markers"]
    unknown_markers = [m for m in markers if not kb.has_control(m["control"])]
    domains = PR.infer_essentials_domains(w.files, w.all_paths, kb.data["essentials_domains"])

    by_level = {lv: sum(1 for f in out if f["level"] == lv) for lv in reversed(LEVELS)}
    run_id = hashlib.sha1((kb.release + "|" + "|".join(sorted(f["id"] for f in out))).encode()).hexdigest()[:10]
    remember(run_id, out)
    blockers = [f["id"] for f in out if f["level"] == "blocker"]
    steps = []
    for ph in kb.phases[cur:]:
        items = [f for f in out if f["phase"] == ph and f["level"] in ("blocker", "gap", "plan")]
        if items:
            steps.append({"phase": ph, "label": PR.PHASE_LABELS[ph], "open": len(items), "top": [f["title"] for f in items[:4]]})
    return {
        "run_id": run_id, "ism_release": kb.release, "root": s["root"], "phase": phase,
        "applicability": {k: appl[k] for k in ("classification", "entity_type", "authorisation_required", "e8_target", "e8_mandate")} | {"pspf": appl["pspf"]["binds"], "irap_required": appl["irap"]["required_for_this_system"]},
        "applicability_full": appl, "summary": {"by_level": by_level, "findings": len(out), "by_tier": {t: sum(1 for f in out if f["tier"] == t) for t in ("rule", "precondition", "heuristic")}},
        "readiness": {"ready_to_proceed_to_authorisation": not blockers, "blockers": len(blockers), "preconditions": pre_rows},
        "essentials_domains": domains, "findings": out, "open_questions": questions, "next_steps": steps,
        "coverage": {"files_scanned": len(w.files), "files_seen": w.total_seen, "truncated": w.truncated, "gitignore_honoured": w.gitignore_honoured,
                     "skipped_large": w.skipped_large[:20], "skipped_generated": w.skipped_generated, "unread_documents": w.unread_documents[:30],
                     "ci_found": ctx["has_ci"], "web": ctx["web"], "ai": ctx["ai"], "agents": ctx["agents"], "cloud_iac": ctx["cloud"],
                     "ism_markers": len(markers), "unknown_ism_markers": unknown_markers[:10]},
        "caveats": ["Static analysis of one directory. Absence findings (confidence low) mean 'not found here', not 'not done'; policies, tickets and platform settings live elsewhere.",
                    "A finding is a signal for the team and its assessor, not an assessment outcome. Only an IRAP assessor sets the Assessment Outcome.",
                    "Only mappings marked direct are enforced by the named mechanism; partial and supporting mappings help evidence a control but do not settle it."],
        "kb": {"release": kb.release, "built": kb.built},
    }


def compact(full: dict, *, level: str = "all", limit: int = 5, offset: int = 0, detail: str = "summary", since: str | None = None) -> dict:
    """Token-efficient view: counts first, top-N findings per level, a cursor to page, deltas when `since` names an earlier run."""
    if level != "all" and level not in LEVELS:
        raise ValueError(f"level must be 'all' or one of {LEVELS}")
    findings = full["findings"]
    delta = None
    if since:
        prev = recall(since)
        if prev is None:
            raise ValueError(f"unknown run id {since!r} (run ids last only while the server runs); call review_project without since")
        cur_ids = {f["id"] for f in findings}
        delta = {"since": since, "new": sorted(cur_ids - prev["ids"]), "resolved": sorted(prev["ids"] - cur_ids)}
        findings = [f for f in findings if f["id"] in delta["new"]]

    def brief(f: dict) -> dict:
        loc = f.get("file", "") + (f":{f['line']}" if f.get("line") else "")
        b = {"id": f["id"], "rule": f["rule"], "title": f["title"], "controls": f["controls"], "confidence": f["confidence"], "fidelity": f["fidelity"]}
        if loc:
            b["at"] = loc
        if f.get("occurrences"):
            b["occurrences"] = f["occurrences"]
        if f.get("urgent"):
            b["urgent"] = True
        b["why"] = f["message"] if len(f["message"]) <= 160 else f["message"][:157] + "…"
        return b

    out = {k: full[k] for k in ("run_id", "ism_release", "phase", "applicability", "summary", "readiness", "kb")}
    out["readiness"] = {**full["readiness"], "preconditions": [{k: p[k] for k in ("id", "status")} | ({"found": p["found"][:2]} if p["found"] else {}) for p in full["readiness"]["preconditions"]]}
    out["essentials_domains"] = {"inferred": [d["domain"] for d in full["essentials_domains"]["domains"]], "evidence_via": "detail=full"}
    if detail == "full":
        out["findings"] = findings
        out["essentials_domains"] = full["essentials_domains"]
        out["coverage"] = full["coverage"]
        out["open_questions"] = full["open_questions"]
        out["next_steps"] = full["next_steps"]
        out["caveats"] = full["caveats"]
        out["level_meaning"] = LEVEL_MEANING
    else:
        lv_list = LEVELS[::-1] if level == "all" else [level]
        shown: dict[str, list] = {}
        more: dict[str, int] = {}
        for lv in lv_list:
            fl = [f for f in findings if f["level"] == lv]
            shown[lv] = [brief(f) for f in fl[offset: offset + limit]]
            if len(fl) > offset + limit:
                more[lv] = len(fl) - offset - limit
        out["findings"] = {k: v for k, v in shown.items() if v}
        if more:
            out["more"] = {**more, "next": f"review_project(level=..., offset={offset + limit}, limit={limit}) or detail=full"}
        out["next_steps"] = full["next_steps"]
        out["coverage"] = {k: full["coverage"][k] for k in ("files_scanned", "truncated", "ci_found", "web", "ai", "agents", "cloud_iac")} | {"unread_documents": len(full["coverage"]["unread_documents"])}
        out["next"] = "interrogate(<finding id>) for evidence and what settles it; level_meaning and caveats are in kb_status."
    if delta:
        out["delta"] = delta
    return out
