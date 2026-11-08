"""Run every detector over a directory and group the results."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import detectors as D
from .files import walk

MAX_LOCATIONS = 20


def fingerprint(fd: D.Finding) -> str:
    ev = re.sub(r"\s+", " ", fd.evidence or "").strip().lower()
    return hashlib.sha1(f"{fd.rule}|{fd.detector}|{fd.file or ''}|{ev if fd.file else fd.message}".encode()).hexdigest()[:8]


def group(findings: list[D.Finding]) -> list[dict]:
    """One finding per (rule, detector, file); lines collapse into occurrences."""
    buckets: dict[tuple, list[D.Finding]] = {}
    for fd in findings:
        buckets.setdefault((fd.rule, fd.detector, fd.file or "", fd.message if not fd.file else ""), []).append(fd)
    out = []
    for (rule, det, file, _), fds in buckets.items():
        fds.sort(key=lambda x: (-D.CONFIDENCES.index(x.confidence), x.line or 0))
        head = fds[0]
        d = {"rule": rule, "detector": det, "confidence": head.confidence, "message": head.message, "kind": head.kind}
        if file:
            d["file"] = file
        if head.line:
            d["line"] = head.line
        if head.evidence:
            d["evidence"] = head.evidence
        lines = sorted({x.line for x in fds if x.line})
        if len(fds) > 1:
            d["occurrences"] = len(fds)
            d["lines"] = lines[:MAX_LOCATIONS]
        if head.extra.get("also_at"):
            d["also_at"] = head.extra["also_at"]
        d["fingerprint"] = fingerprint(head)
        out.append(d)
    return out


def scan_path(root: Path, *, max_files: int = 20000, exclude: list[str] | None = None, use_git: bool = True) -> dict:
    root = Path(root).expanduser()
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    w = walk(root, max_files=max_files, extra_excludes=exclude, use_git=use_git)
    findings: list[D.Finding] = []
    for f in w.files:
        for det in D.PATTERNS:
            findings.extend(det.run(f))
    ctx = D.detect_context(w.files, w.all_paths)
    findings.extend(D.repo_level(w.files, w.all_paths, ctx))
    markers = []
    for f in w.files:
        for i, ln in enumerate(f.lines):
            m = re.search(r"\bism:\s*((?:ISM-\d{4}\s*,?\s*)+)", ln)
            if m and "ism-review" not in ln:
                markers.extend({"control": c.upper(), "file": f.rel, "line": i + 1} for c in re.findall(r"ISM-\d{4}", m.group(1), re.I))
    return {"root": str(root.resolve()), "files": w.files, "all_paths": w.all_paths, "walk": w, "context": ctx,
            "findings": group(findings), "markers": markers}
