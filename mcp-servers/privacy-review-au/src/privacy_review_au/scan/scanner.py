"""Run every detector over a directory, build the personal-information inventory, and join
findings to the knowledge base."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .. import observations as O
from ..kb import KB
from . import detectors as D
from . import inventory as I
from .files import walk

# Prose that describes the repository's tooling or history rather than the system being reviewed.
_NOT_DESIGN = re.compile(r"(?:^|/)(?:changelog|changes|history|license|licence|notice|code_of_conduct|contributing|security|authors)(?:\.\w+)?$",
                         re.I)

MAX_LOCATIONS = 20


def _cite_short(kb: KB, c: dict) -> dict:
    s = kb.source(c["source"])
    out = {"source": c["source"], "citation": s["citation"] if s else c["source"], "pinpoint": c.get("pinpoint", "")}
    if s and s.get("status") and s["type"] != "legislation":
        out["status"] = s["status"]
    if c.get("secondary"):
        out["quoted_from"] = c.get("quote_source")
    return out


def join_entries(kb: KB, ids: list[str], as_at: dt.date, include_heuristics: bool = True) -> list[dict]:
    """KB entry briefs for a finding: title, provisions, commencement and key citations."""
    entries = []
    for eid in ids:
        e = kb.entry(eid)
        if not e or (e["kind"] == "heuristic" and not include_heuristics):
            continue
        pending = e.get("commences") and dt.date.fromisoformat(e["commences"]) > as_at
        entries.append({"id": eid, "kind": e["kind"], "title": e["title"], "provisions": e["provisions"],
                        **({"commences": e["commences"], "not_yet_in_force": True} if pending else {}),
                        "key_citations": [_cite_short(kb, c) for c in e["citations"][:3]]})
    return entries


def coverage(files: list, unread: list[str], dumps: list[str]) -> dict:
    """What kinds of material were examined, so 'not found' is only ever claimed about what was looked at."""
    c = {"code": 0, "markup": 0, "infrastructure": 0, "schema": 0, "documents": 0, "privacy_policies": 0, "tests": 0}
    for f in files:
        ext = D._ext(f)
        if f.is_test:
            c["tests"] += 1
        elif f.is_prose:
            c["documents"] += 1
        elif ext in {".sql", ".prisma", ".graphql", ".gql"}:
            c["schema"] += 1
        elif ext in D.MARKUP_EXT:
            c["markup"] += 1
        elif ext in D.CODE_EXT:
            c["code"] += 1
        elif ext in D.IAC_EXT or ext == ".dockerfile":
            c["infrastructure"] += 1
        if D.POLICY_PATH.search(f.lower_rel) and not f.is_test:
            c["privacy_policies"] += 1
    c["code_examined"] = (c["code"] + c["markup"] + c["infrastructure"] + c["schema"]) > 0
    c["unread_documents"] = unread[:50]
    c["data_files_not_parsed"] = dumps[:50]
    return c


def _loc(fd: D.Finding) -> str:
    return (fd.file or "(repository)") + (f":{fd.line}" if fd.line else "")


def _norm(ev: str | None) -> str:
    return re.sub(r"\s+", " ", ev or "").strip().lower()


def _group(findings: list[D.Finding]) -> list[tuple[D.Finding, list[str]]]:
    """Collapse findings that share a cause, in two passes:
    1. one finding per detector, KB entries and file (a pixel snippet spread over three lines is one pixel);
    2. merge those per-file findings whose evidence is identical across files (a file copied into
       static/ and public/, or a snippet pasted into many templates)."""
    per_file: dict[tuple, list[D.Finding]] = {}
    for fd in findings:
        key = (fd.detector, tuple(sorted(fd.entries)), fd.file or "", "" if (fd.file and fd.evidence) else fd.message)
        per_file.setdefault(key, []).append(fd)
    merged: dict[tuple, tuple[D.Finding, list[str]]] = {}
    for (det, ents, file, _), fds in per_file.items():
        fds.sort(key=lambda x: (-D.SEVERITIES.index(x.severity), x.line or 0))
        head = fds[0]
        evidence = frozenset(_norm(x.evidence) for x in fds) if file and any(x.evidence for x in fds) else None
        key = (det, ents, evidence) if evidence else (det, ents, file, head.message)
        locs = [_loc(x) for x in fds]
        if key in merged:
            first, all_locs = merged[key]
            all_locs.extend(locs)
            if D.SEVERITIES.index(head.severity) > D.SEVERITIES.index(first.severity):
                first.severity = head.severity
        else:
            merged[key] = (head, locs)
    return list(merged.values())


def scan_path(kb: KB, root: Path, *, max_files: int = 20000, exclude: list[str] | None = None,
              entity_type: str | None = None, include_heuristics: bool = True, min_severity: str = "info",
              as_at: dt.date | None = None, kind: str = "auto", sensitive_context: bool | None = None,
              use_git: bool = True, digital_id_role: str | None = None) -> dict:
    root = Path(root).expanduser()
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    as_at = as_at or dt.date.today()
    w = walk(root, max_files=max_files, extra_excludes=exclude, use_git=use_git)
    findings: list[D.Finding] = []
    for f in w.files:
        for det in D.PATTERNS:
            findings.extend(det.run(f))
        findings.extend(D.field_detectors(f))
        findings.extend(D.fixture_pii(f))
    findings.extend(D.processor_findings(w.files))

    detected_kind, kind_reasons = D.system_kind(w.files)
    sys_kind = detected_kind if kind == "auto" else kind
    sens_terms = D.sensitive_context_terms(w.files)
    if sensitive_context is False:
        sens_terms = []
    elif sensitive_context is True and not sens_terms:
        sens_terms = ["(stated by the team)"]
    inv = I.build(w.files, findings)
    findings.extend(D.repo_level(w.files, findings, w.binary_dumps, entity_type, sys_kind, sens_terms,
                                 inv["handles_personal_information"]))
    D.link_digital_id(findings, digital_id_role)
    digid_terms = D.digital_id_terms(w.files)

    floor = D.SEVERITIES.index(min_severity)
    out, by_entry = [], {}
    grouped = sorted(_group(findings), key=lambda g: (-D.SEVERITIES.index(g[0].severity), g[0].file or "", g[0].line or 0))
    for fd, locs in grouped:
        entries = join_entries(kb, fd.entries, as_at, include_heuristics)
        if not entries or D.SEVERITIES.index(fd.severity) < floor:
            continue
        for x in entries:
            by_entry[x["id"]] = by_entry.get(x["id"], 0) + 1
        d = fd.as_dict()
        d["id"] = f"F{len(out) + 1:04d}"
        d["kb"] = entries
        d["tier"] = "rule" if any(x["kind"] == "rule" for x in entries) else "heuristic"
        if len(locs) > 1:
            d["occurrences"] = len(locs)
            d["also_at"] = locs[1:MAX_LOCATIONS]
        out.append(d)

    summary = {s: sum(1 for f in out if f["severity"] == s) for s in reversed(D.SEVERITIES)}
    by_provision: dict[str, int] = {}
    for f in out:
        for e in f["kb"]:
            for p in e["provisions"][:1]:
                by_provision[p] = by_provision.get(p, 0) + 1
    policies = [f.rel for f in w.files if D.POLICY_PATH.search(f.lower_rel) and not f.is_test]
    return {
        "root": str(root.resolve()), "as_at": as_at.isoformat(), "files_scanned": len(w.files), "files_seen": w.total_seen,
        "truncated": w.truncated,
        "noise_control": {"gitignore_honoured": w.gitignore_honoured, "skipped_generated": len(w.skipped_generated),
                          "skipped_large_files": w.skipped_large[:50], "ignored_by_marker": w.ignored_by_marker[:50]},
        "context": {"system_kind": sys_kind, "system_kind_detected": detected_kind, "system_kind_reasons": kind_reasons,
                    "sensitive_context_terms": sens_terms, "privacy_policy_files": policies[:10],
                    "digital_id_terms": digid_terms, "digital_id_role": digital_id_role},
        "data_inventory": inv,
        "coverage": coverage(w.files, w.unread_documents, w.binary_dumps),
        "doc_mentions": O.mentions([f for f in w.files if f.is_prose and not f.is_test and not _NOT_DESIGN.search(f.lower_rel)
                                   and not D.POLICY_PATH.search(f.lower_rel)]),
        "summary": {"by_severity": summary, "by_tier": {t: sum(1 for f in out if f["tier"] == t) for t in ("rule", "heuristic")},
                    "by_primary_provision": dict(sorted(by_provision.items(), key=lambda kv: -kv[1])), "by_entry": by_entry},
        "findings": out,
        "caveats": [
            "Signals, not legal conclusions: each finding names the requirement it bears on; exceptions and context (see get_entry) decide whether it is a contravention.",
            "Static analysis sees only this directory. Policies, PIAs, contracts and runbooks kept elsewhere are not visible.",
            "The APPs bind APP entities. Most small businesses (turnover of $3m or less) are exempt unless s 6D(4) applies; use assess_applicability. The Schedule 2 tort applies regardless.",
            "Not legal advice.",
        ],
        "kb_built": kb.built,
    }
