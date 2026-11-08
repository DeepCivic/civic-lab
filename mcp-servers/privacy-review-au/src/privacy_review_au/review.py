"""Privacy review: scan what is available, rank what it shows, and say what is still unknown.

This is the main entry point. It does not need anyone's answers. It reads code and prose documents,
takes any observations the agent has recorded from other material (PDFs, Confluence, the team), and returns:

- findings at four levels:
    critical  the facts resemble a decided case that went against the entity (final decisions only);
    high      reads as an APP contravention if the facts are as they appear (rule tier, firm evidence);
    caution   not enough information, but this may be a privacy issue (heuristics, weak signals,
              absences, and passages in documents that need reading);
    info      recorded for completeness;
- gaps: specific outstanding questions, each with why it matters, what evidence would settle it and
  where the scan looked;
- coverage: what kinds of material were examined, so 'not found' is never claimed about what was not read;
- threshold readiness: where a privacy threshold assessment would land on current evidence.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import __version__
from . import observations as O
from . import precedents as P
from . import threshold as T
from .kb import KB
from .scan import detectors as D
from .scan.files import TEXT_EXT, UNREAD_DOC_EXT, SourceFile, walk
from .scan.scanner import join_entries, scan_path

LEVELS = ["info", "caution", "high", "critical"]
LEVEL_MEANING = {
    "critical": "The facts resemble a decided case that went against the entity. Check the distinguishing facts first.",
    "high": "Reads as an APP contravention if the facts are as they appear. Check the exceptions.",
    "caution": "Not enough information to say, but this may be a privacy issue. The questions say what to confirm.",
    "info": "Recorded for completeness.",
}
DOC_EXT = {".md", ".mdx", ".txt", ".rst", ".adoc", ".html", ".htm"}


# --------------------------------------------------------------------------- inputs

def _read_documents(paths: list[Path]) -> tuple[list[SourceFile], list[str]]:
    files: list[SourceFile] = []
    unread: list[str] = []
    for p in paths:
        if p.is_dir():
            w = walk(p, max_files=2000)
            files += [SourceFile(f.path, f"{p.name}/{f.rel}", f.text) for f in w.files if f.path.suffix.lower() in DOC_EXT]
            unread += [f"{p.name}/{r}" for r in w.unread_documents]
        elif p.is_file():
            ext = p.suffix.lower()
            if ext in UNREAD_DOC_EXT:
                unread.append(p.name)
            elif ext in TEXT_EXT or ext in DOC_EXT:
                files.append(SourceFile(p, p.name, p.read_text(encoding="utf-8", errors="replace")))
            else:
                unread.append(p.name)
        else:
            raise ValueError(f"document not found: {p}")
    return files, unread


def _merge_mentions(a: dict, b: dict, cap: int = 6) -> dict:
    out = {k: list(v) for k, v in a.items()}
    for k, v in b.items():
        out[k] = (out.get(k, []) + v)[:cap]
    return out


# --------------------------------------------------------------------------- levels

def _max_sev(kb: KB, ids: tuple[str, ...]) -> str:
    sevs = [(kb.entry(i) or {}).get("severity", "medium") for i in ids]
    return max(sevs or ["medium"], key=D.SEVERITIES.index)


def _confirm(kb: KB, f: dict) -> None:
    qs, exc = [], []
    for e in f.get("kb", []):
        full = kb.entry(e["id"]) or {}
        qs += [q for q in full.get("questions_for_agent", []) if q not in qs]
        exc += [x for x in full.get("exceptions", []) if x not in exc]
    if qs:
        f["to_confirm"] = qs[:5]
    if exc:
        f["exceptions_to_check"] = exc[:3]


def _level(f: dict, kind: O.Kind | None) -> str:
    if f.get("precedent"):
        return "critical" if f["precedent"]["has_final_decision"] else "high"
    if f["severity"] == "info":
        return "info"
    rules = [e for e in f.get("kb", []) if e["kind"] == "rule"]
    if rules and all(e.get("not_yet_in_force") for e in rules):
        return "caution"
    if kind is not None:
        return kind.level
    if f.get("tier") == "rule" and f["severity"] in ("high", "critical") and f.get("confidence") != "low":
        return "high"
    return "caution"


# --------------------------------------------------------------------------- the review

def build(kb: KB, path: Path | None = None, *, documents: list[Path] | None = None, observations: list[dict] | None = None,
          answers: dict[str, bool] | None = None, entity_type: str | None = None, kind: str = "auto",
          sensitive_context: bool | None = None, exclude: list[str] | None = None, digital_id_role: str | None = None,
          project_name: str | None = None, project_description: str | None = None, as_at: dt.date | None = None,
          use_git: bool = True) -> dict:
    """Run the review. Returns {'review': ..., 'threshold': ...}: the threshold result is built from the same evidence."""
    as_at = as_at or dt.date.today()
    obs = O.normalise(observations, answers)
    if sensitive_context is None and any(o["present"] and O.BY_ID[o["kind"]].sensitive for o in obs):
        sensitive_context = True
    role = digital_id_role if digital_id_role in ("accredited_entity", "relying_party") else None

    scan = None
    if path is not None:
        scan = scan_path(kb, path, exclude=exclude, entity_type=entity_type, kind=kind, sensitive_context=sensitive_context,
                         min_severity="info", as_at=as_at, use_git=use_git, digital_id_role=role)
    doc_files, unread = _read_documents(documents or [])
    if scan is None and (doc_files or unread or obs):
        scan = {"findings": [], "data_inventory": {}, "context": {}, "doc_mentions": {},
                "coverage": {"code": 0, "markup": 0, "infrastructure": 0, "schema": 0, "documents": 0, "privacy_policies": 0,
                             "tests": 0, "code_examined": False, "unread_documents": [], "data_files_not_parsed": []}}
    if scan is not None:
        scan["doc_mentions"] = _merge_mentions(scan.get("doc_mentions") or {}, O.mentions(doc_files))
        scan["coverage"]["documents"] += len(doc_files)
        scan["coverage"]["documents_supplied"] = [f.rel for f in doc_files][:50]
        scan["coverage"]["unread_documents"] = (scan["coverage"].get("unread_documents") or []) + unread

    findings: list[dict] = []
    for f in (scan or {}).get("findings", []):
        f = dict(f)
        f["source_type"] = "code"
        p = P.match(f)
        if p:
            f["precedent"] = P.describe(kb, p)
        f["level"] = _level(f, None)
        findings.append(f)
    for o in obs:
        k = O.BY_ID[o["kind"]]
        if not o["present"] or not k.entries:
            continue
        entries = join_entries(kb, list(k.entries), as_at)
        f = {"detector": f"observation:{k.id}", "severity": _max_sev(kb, k.entries), "confidence": "stated",
             "message": f"{k.label}: {o['fact']}", "file": o["source"], "evidence": o["fact"], "kb": entries,
             "tier": "rule" if any(e["kind"] == "rule" for e in entries) else "heuristic", "source_type": "observation"}
        if k.precedent:
            f["precedent"] = P.describe(kb, P.BY_ID[k.precedent])
        f["level"] = _level(f, k)
        findings.append(f)
    for f in findings:
        _confirm(kb, f)
    findings.sort(key=lambda f: (-LEVELS.index(f["level"]), -D.SEVERITIES.index(f["severity"]), f.get("file") or "", f.get("line") or 0))
    for i, f in enumerate(findings, 1):
        if "id" in f:
            f["scan_id"] = f["id"]
        f["id"] = f"F{i:03d}"

    if project_name is None and path is None and documents:
        project_name = Path(documents[0]).name
    th = T.assess(kb, {**scan, "findings": findings} if scan is not None else None, answers, entity_type=entity_type,
                  project_name=project_name, project_description=project_description, as_at=as_at,
                  digital_id_role=digital_id_role, observations=obs)
    rows = {r["id"]: r for r in th["questions"]}

    # Passages in documents that bear on a finding-type concern, where nothing else has settled it yet.
    observed_kinds = {o["kind"] for o in obs}
    n = len(findings)
    for kid, ms in ((scan or {}).get("doc_mentions") or {}).items():
        k = O.BY_ID[kid]
        if not k.entries or kid in observed_kinds or (k.question and rows[k.question]["answer"] != "indicated"):
            continue
        n += 1
        m = ms[0]
        f = {"id": f"F{n:03d}", "detector": "document-mention", "severity": "low", "confidence": "low", "level": "caution",
             "source_type": "document", "tier": "document",
             "message": f"Documents mention {k.label.lower()}. Read the passage and record what it actually says as an "
                        f"observation of kind '{k.id}' (present: false if it rules this out).",
             "file": m["file"], "line": m["line"], "evidence": m["excerpt"], "kb": join_entries(kb, list(k.entries), as_at),
             "observation_kind": k.id}
        if len(ms) > 1:
            f["occurrences"] = len(ms)
            f["also_at"] = [f"{x['file']}:{x['line']}" for x in ms[1:]]
        _confirm(kb, f)
        findings.append(f)

    gaps = _gaps(kb, th, rows, findings, scan, path is not None, bool(documents))
    by_level = {lv: sum(1 for f in findings if f["level"] == lv) for lv in reversed(LEVELS)}
    name = th["project"]
    review = {
        "project": name, "as_at": as_at.isoformat(),
        "headline": _headline(by_level, gaps),
        "summary": {"by_level": by_level, "gaps": len(gaps), "high_priority_gaps": sum(1 for g in gaps if g["priority"] == "high")},
        "findings": findings, "gaps": gaps,
        "coverage": (scan or {}).get("coverage") or {"code_examined": False, "documents": 0},
        "threshold_readiness": {
            "outcome": th["outcome"], "outcome_label": th["outcome_label"], "reasons": th["reasons"],
            "answers": {a: [r["id"] for r in th["questions"] if r["answer"] == a]
                        for a in ("yes", "no", "indicated", "unknown", "not detected")},
            "note": "Where a privacy threshold assessment would land on current evidence. Use threshold_assessment for the record."},
        "data_inventory": (scan or {}).get("data_inventory"),
        "document_mentions": (scan or {}).get("doc_mentions") or {},
        "observations": obs,
        "context": (scan or {}).get("context", {}),
        "level_definitions": LEVEL_MEANING,
        "caveats": [
            "Signals, not legal conclusions. A critical finding says the facts resemble a case that was lost; the distinguishing "
            "questions and exceptions decide whether they really do.",
            "Code shows what a system can do; documents show what was intended. Neither shows what happens in production or what "
            "people were told. Gaps list what is still unknown.",
            "The APPs bind APP entities; most small businesses are exempt (see assess_applicability). Commonwealth law only.",
            "Not legal advice.",
        ],
        "kb_built": kb.built, "tool_version": __version__,
    }
    review["report_markdown"] = render_markdown(review)
    return {"review": review, "threshold": th}


def _headline(by_level: dict, gaps: list[dict]) -> str:
    parts = [f"{by_level[lv]} {lv}" for lv in ("critical", "high", "caution") if by_level.get(lv)]
    hp = sum(1 for g in gaps if g["priority"] == "high")
    return (", ".join(parts) or "No findings") + f"; {len(gaps)} open question(s)" + (f", {hp} high priority." if hp else ".")


def _gaps(kb: KB, th: dict, rows: dict, findings: list[dict], scan: dict | None, had_path: bool, had_docs: bool) -> list[dict]:
    gaps: list[dict] = []
    cov = (scan or {}).get("coverage") or {}
    looked = _looked(cov, had_path)
    for r in th["questions"]:
        if r["answer"] not in ("unknown", "indicated"):
            continue
        q = T.BY_QUESTION[r["id"]]
        related = [f["id"] for f in findings if f["level"] != "info" and {e["id"] for e in f.get("kb", [])} & set(q.entries)]
        kinds = [k.id for k in O.KINDS if k.question == r["id"]]
        gaps.append({
            "id": r["id"], "type": "threshold_question", "priority": "high" if r["weight"] in ("gate", "high") else "medium",
            "question": r["question"], "status": r["answer"],
            "why_it_matters": T.WEIGHT_WHY[r["weight"]] + (f" Bears on findings {', '.join(related[:6])}." if related else ""),
            **({"evidence_so_far": r["evidence"]} if r["evidence"] else {}),
            "what_would_resolve": T.RESOLVE.get(r["id"], ""),
            "record_as": kinds, "looked_in": looked})
    for o in th["open_questions"]:
        regime = o["id"].startswith("R-DIGID") or (o["id"] in ("large_scale", "digital_id_system") and rows[o["id"]]["answer"] == "yes")
        if not regime:
            continue
        gaps.append({"id": f"{o['id']}-regime", "type": "regime", "priority": "medium", "question": o["question"],
                     "why_it_matters": "Another Act adds obligations on top of the APPs if this applies.",
                     "what_would_resolve": ("Who the system serves (a Commonwealth, State or Territory body?) and how many people's records it "
                                            "stores or processes." if o["id"] == "large_scale" else
                                            "The entity's role in the Digital ID System, and the system design for this point.")})
    for f in findings:
        if f["level"] == "critical":
            p = f["precedent"]
            gaps.append({"id": f"{f['id']}-facts", "type": "distinguishing_facts", "priority": "high",
                         "question": f"Do the facts behind {f['id']} really match '{p['title']}'?",
                         "why_it_matters": "If they do, the project is on the same side as "
                                           + "; ".join(d["citation"] for d in p["decisions"] if d["final"]) + ".",
                         "what_would_resolve": " ".join(p["distinguish_by"] or f.get("to_confirm") or [p["fact_pattern"]]),
                         "finding": f["id"]})
    if cov.get("unread_documents"):
        gaps.append({"id": "unread-documents", "type": "input", "priority": "high",
                     "question": f"{len(cov['unread_documents'])} document(s) could not be read by the scanner (PDF, Word, slides ...).",
                     "why_it_matters": "Design and requirements documents often say what code cannot: purpose, scale, who is affected, "
                                       "where data goes.",
                     "what_would_resolve": "Read them and submit what they say as observations (list_observation_kinds), then run the review again.",
                     "files": cov["unread_documents"][:20]})
    if not cov.get("documents") and not had_docs:
        gaps.append({"id": "no-documents", "type": "input", "priority": "medium",
                     "question": "No design, requirements or architecture documents were examined.",
                     "why_it_matters": "The code shows what the system can do, not why, for whom, or at what scale.",
                     "what_would_resolve": "Pass documents=[...] (Markdown, text or HTML), or read other material and submit observations."})
    if not cov.get("code_examined"):
        gaps.append({"id": "no-code", "type": "input", "priority": "medium",
                     "question": "No code, templates, schemas or infrastructure configuration were examined.",
                     "why_it_matters": "Questions code can usually answer (sensitive fields, tracking, recipients, security settings) "
                                       "stay unknown rather than 'not detected'.",
                     "what_would_resolve": "Pass the repository path, or record what is known as observations."})
    order = {"high": 0, "medium": 1, "low": 2}
    gaps.sort(key=lambda g: order[g["priority"]])
    return gaps


def _looked(cov: dict, had_path: bool) -> str:
    if not cov:
        return "nothing was scanned"
    bits = [f"{cov.get(k, 0)} {k}" for k in ("code", "markup", "schema", "infrastructure", "documents") if cov.get(k)]
    return ("scanned " + ", ".join(bits)) if bits else ("the repository had no readable code or documents" if had_path else "nothing was scanned")


# --------------------------------------------------------------------------- interrogation

def interrogate(kb: KB, bundle: dict, topic: str) -> dict:
    """Everything known about one topic: a threshold question, an observation kind, a KB entry, or a finding id."""
    rv, th = bundle["review"], bundle["threshold"]
    topic = topic.strip()
    rows = {r["id"]: r for r in th["questions"]}
    finding = next((f for f in rv["findings"] if f["id"] == topic), None)
    if finding:
        entry_ids = [e["id"] for e in finding.get("kb", [])]
        qs = [q.id for q in T.QUESTIONS if set(q.entries) & set(entry_ids)]
        return {"topic": topic, "type": "finding", "finding": finding, "level_meaning": LEVEL_MEANING[finding["level"]],
                "entries": [_entry_view(kb, e) for e in entry_ids],
                "threshold_questions": [rows[q] for q in qs], "gaps": [g for g in rv["gaps"] if g.get("finding") == topic]}
    if topic in rows:
        q = T.BY_QUESTION[topic]
        kinds = [k for k in O.KINDS if k.question == topic]
        return {"topic": topic, "type": "threshold_question", "row": rows[topic], "weight_meaning": T.WEIGHT_WHY[q.weight],
                "guidance": q.guidance, "what_would_resolve": T.RESOLVE.get(topic, ""),
                "evidence_for": rows[topic]["evidence"],
                "evidence_against": [f"{o['fact']} ({o['source']})" for o in rv["observations"]
                                     if not o["present"] and O.BY_ID[o["kind"]].question == topic],
                "document_mentions": {k.id: rv["document_mentions"][k.id] for k in kinds if k.id in rv["document_mentions"]},
                "findings": [_brief(f) for f in rv["findings"] if {e["id"] for e in f.get("kb", [])} & set(q.entries)],
                "record_as": [k.brief() for k in kinds], "related_entries": list(q.entries),
                "looked_in": _looked(rv["coverage"], True), "gap": next((g for g in rv["gaps"] if g["id"] == topic), None)}
    if topic in O.BY_ID:
        k = O.BY_ID[topic]
        out = {"topic": topic, "type": "observation_kind", "kind": k.brief(),
               "observations": [o for o in rv["observations"] if o["kind"] == topic],
               "findings": [_brief(f) for f in rv["findings"] if f["detector"] == f"observation:{topic}" or f.get("observation_kind") == topic
                            or {e["id"] for e in f.get("kb", [])} & set(k.entries)]}
        if k.question:
            out["threshold_question"] = rows[k.question]
        if k.precedent:
            out["precedent"] = P.describe(kb, P.BY_ID[k.precedent])
        return out
    if kb.entry(topic):
        return {"topic": topic, "type": "entry", "entry": _entry_view(kb, topic),
                "findings": [_brief(f) for f in rv["findings"] if any(e["id"] == topic for e in f.get("kb", []))],
                "threshold_questions": [rows[q.id] for q in T.QUESTIONS if topic in q.entries],
                "precedent_patterns": [P.describe(kb, p) for p in P.PATTERNS if p.entry == topic]}
    raise ValueError(f"unknown topic {topic!r}: give a finding id (F001), a threshold question id, an observation kind or a KB entry id")


def _brief(f: dict) -> dict:
    return {k: f[k] for k in ("id", "level", "message", "file", "line", "source_type") if k in f} | \
        ({"precedent": f["precedent"]["title"]} if f.get("precedent") else {})


def _entry_view(kb: KB, eid: str) -> dict:
    e = kb.entry(eid) or {}
    return {k: e[k] for k in ("id", "kind", "title", "provisions", "requirement", "contravention", "concern", "exceptions",
                              "questions_for_agent", "remediation", "commences") if k in e}


# --------------------------------------------------------------------------- report

def _esc(s: object) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_markdown(r: dict) -> str:
    L = [f"# Privacy review: {r['project']}", "",
         f"_Generated {r['as_at']} by privacy-review-au {r['tool_version']} (knowledge base {r['kb_built']}). "
         "Signals for the team and its privacy officer, not legal advice._", "", f"**{r['headline']}**", ""]
    for lv in ("critical", "high", "caution"):
        fs = [f for f in r["findings"] if f["level"] == lv]
        if not fs:
            continue
        L += [f"## {lv.capitalize()} ({len(fs)})", "", f"_{LEVEL_MEANING[lv]}_", ""]
        for f in fs:
            loc = (f.get("file") or "(repository)") + (f":{f['line']}" if f.get("line") else "")
            more = f" (+{f['occurrences'] - 1} more)" if f.get("occurrences", 1) > 1 else ""
            prov = ", ".join(dict.fromkeys(p for e in f.get("kb", []) for p in e["provisions"][:1]))
            L.append(f"- **{f['id']}** {_esc(f['message'])} `{_esc(loc)}`{more}" + (f" ({prov})" if prov else ""))
            if f.get("precedent"):
                p = f["precedent"]
                cases = "; ".join(d["citation"] + ("" if d["final"] else f" [{d['status'][:60]}]") for d in p["decisions"])
                L.append(f"  - Resembles: {p['title']}. {cases}")
            for q in (f.get("to_confirm") or [])[:3] if lv != "caution" else (f.get("to_confirm") or [])[:2]:
                L.append(f"  - Confirm: {q}")
        L.append("")
    if r["gaps"]:
        L += ["## Open questions", ""]
        for g in r["gaps"]:
            L.append(f"- **[{g['priority']}]** {_esc(g['question'])}")
            L.append(f"  - Why: {_esc(g['why_it_matters'])}")
            if g.get("what_would_resolve"):
                L.append(f"  - Evidence that would settle it: {_esc(g['what_would_resolve'])}")
        L.append("")
    t = r["threshold_readiness"]
    L += ["## Threshold readiness", "", f"{t['outcome_label']}", ""] + [f"- {x}" for x in t["reasons"]] + [""]
    cov = r["coverage"]
    L += ["## Coverage", "", _looked(cov, True) + "." + (f" Not read: {', '.join(cov['unread_documents'][:10])}." if cov.get("unread_documents") else ""), ""]
    return "\n".join(L)
