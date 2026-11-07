"""au-privacy-review: serve the MCP server, or review a project from the command line.

  au-privacy-review                         serve over stdio (what MCP clients launch)
  au-privacy-review serve [--http --root DIR ...] [--allow-live]
  au-privacy-review review PATH [--doc DOCS ...] [--observations obs.json] [--json | --out review.md] [--fail-on high]
  au-privacy-review threshold PATH [--doc DOCS] [--observations obs.json] [--answers answers.json] [--json | --out record.md]
  au-privacy-review questions               list the threshold questions
  au-privacy-review kinds                   list the observation kinds (for an observations file)
  au-privacy-review scan PATH [--json] [--min-severity S]    the raw detector signals
  au-privacy-review status

`review` exits 1 when a finding is at or above --fail-on (default: high), so it can gate CI.
`scan` exits 1 when there is a high or critical rule-tier finding.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

KINDS = ["auto", "application", "library", "unknown"]


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("path", type=Path)
    p.add_argument("--entity-type", default=None, choices=["organisation", "agency"])
    p.add_argument("--system-kind", default="auto", choices=KINDS)
    p.add_argument("--exclude", action="append", default=None, help="relative path to skip (repeatable)")
    p.add_argument("--digital-id-role", default=None, choices=["none", "accredited_entity", "relying_party"],
                   help="role in the Australian Government Digital ID System (links the Digital ID Act 2024 rules)")
    p.add_argument("--json", action="store_true")


def _evidence(p: argparse.ArgumentParser) -> None:
    p.add_argument("--doc", action="append", type=Path, default=None, help="design/requirements document or folder (repeatable)")
    p.add_argument("--observations", type=Path, help="JSON list of {kind, fact, source, present}")
    p.add_argument("--answers", type=Path, help="JSON object of question id -> true/false")
    p.add_argument("--name")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="au-privacy-review", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve")
    s.add_argument("--http", action="store_true")
    s.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    s.add_argument("--root", action="append", default=[], help="directory clients may scan (repeatable; required with --http)")
    s.add_argument("--allow-live", action="store_true", help="enable probe_deployment (network)")
    rv = sub.add_parser("review", help="privacy review: findings by level, open questions, coverage")
    _common(rv)
    _evidence(rv)
    rv.add_argument("--min-level", default="caution", choices=["info", "caution", "high", "critical"])
    rv.add_argument("--fail-on", default="high", choices=["critical", "high", "caution", "never"])
    rv.add_argument("--out", type=Path, help="write the review (Markdown) to this file")
    th = sub.add_parser("threshold", help="threshold assessment: is a PIA needed?")
    _common(th)
    _evidence(th)
    th.add_argument("--description")
    th.add_argument("--out", type=Path, help="write the draft record (Markdown) to this file")
    sc = sub.add_parser("scan", help="the underlying signals")
    _common(sc)
    sc.add_argument("--min-severity", default="low", choices=["info", "low", "medium", "high", "critical"])
    sub.add_parser("questions")
    sub.add_parser("kinds")
    sub.add_parser("status")
    a = ap.parse_args(argv)

    if a.cmd in (None, "serve"):
        if getattr(a, "allow_live", False):
            os.environ["AU_PRIVACY_REVIEW_LIVE"] = "1"
        if getattr(a, "root", None):
            os.environ["AU_PRIVACY_REVIEW_ROOTS"] = os.pathsep.join(str(Path(r).resolve()) for r in a.root)
        from .server import main as serve

        serve(http=getattr(a, "http", False), host=getattr(a, "host", "127.0.0.1"), port=getattr(a, "port", 8000))
        return
    from . import kb as _kb
    from . import threshold as _th

    if a.cmd == "status":
        from .server import kb_status

        print(json.dumps(kb_status(), indent=1))
        return
    if a.cmd == "kinds":
        from .observations import KINDS

        for k in KINDS:
            print(f"{k.id:36} {k.label}\n{'':36} look for: {k.look_for}")
        return
    if a.cmd == "questions":
        for q in _th.questions():
            print(f"{q['id']:30} [{q['weight']:6}] {'code+team' if q['detectable_from_code'] else 'team only':9}  {q['question']}")
        return
    from .scan.scanner import scan_path

    kb = _kb.load()
    if a.cmd in ("review", "threshold"):
        from . import review as _rv

        b = _rv.build(kb, a.path, documents=a.doc, observations=json.loads(a.observations.read_text(encoding="utf-8")) if a.observations else None,
                      answers=json.loads(a.answers.read_text(encoding="utf-8")) if a.answers else None, entity_type=a.entity_type,
                      kind=a.system_kind, exclude=a.exclude, digital_id_role=a.digital_id_role, project_name=a.name,
                      project_description=getattr(a, "description", None))
    if a.cmd == "review":
        r = b["review"]
        floor = _rv.LEVELS.index(a.min_level)
        r["findings"] = [f for f in r["findings"] if _rv.LEVELS.index(f["level"]) >= floor]
        if a.out:
            a.out.write_text(r["report_markdown"], encoding="utf-8")
        if a.json:
            print(json.dumps(r, indent=1))
        elif not a.out:
            print(r["report_markdown"])
        else:
            print(f"{r['headline']}\nReview written to {a.out}.")
        fail = a.fail_on != "never" and any(_rv.LEVELS.index(f["level"]) >= _rv.LEVELS.index(a.fail_on) for f in r["findings"])
        sys.exit(1 if fail else 0)
    if a.cmd == "threshold":
        res = b["threshold"]
        if a.out:
            a.out.write_text(res["report_markdown"], encoding="utf-8")
        if a.json:
            print(json.dumps(res, indent=1))
        elif not a.out:
            print(res["report_markdown"])
        else:
            print(f"{res['outcome_label']}\nDraft record written to {a.out}. Unanswered: {', '.join(res['factors']['unanswered']) or 'none'}")
        return

    res = scan_path(kb, a.path, min_severity=a.min_severity, entity_type=a.entity_type, kind=a.system_kind, exclude=a.exclude,
                    digital_id_role=a.digital_id_role if a.digital_id_role != "none" else None)
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        ctx = res["context"]
        print(f"{res['files_scanned']} files scanned under {res['root']}  (as at {res['as_at']}; {ctx['system_kind']})")
        print("severity:", ", ".join(f"{k}={v}" for k, v in res["summary"]["by_severity"].items() if v) or "none")
        for f in res["findings"]:
            loc = f"{f.get('file', '(repository)')}" + (f":{f['line']}" if f.get("line") else "")
            more = f"  (+{f['occurrences'] - 1} more)" if f.get("occurrences", 1) > 1 else ""
            ids = ", ".join(e["id"] for e in f["kb"])
            print(f"[{f['severity'].upper():8}] {f['tier']:9} {loc}{more}\n    {f['message']}\n    -> {ids}")
    sys.exit(1 if any(f["severity"] in ("high", "critical") and f["tier"] == "rule" for f in res["findings"]) else 0)
