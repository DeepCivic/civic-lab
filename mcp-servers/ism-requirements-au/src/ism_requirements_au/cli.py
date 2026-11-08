"""ism-requirements-au: serve the MCP server, or review a project and verify its control manifest from the command line.

  ism-requirements-au                          serve over stdio (what MCP clients launch)
  ism-requirements-au serve [--http --root DIR ...]
  ism-requirements-au review PATH --entity-type T [--classification C] [--phase P] [--json] [--fail-on blocker|gap|never]
  ism-requirements-au verify [PATH] [--manifest FILE] [--strict]     offline check of .ism/controls.yaml (exit 1 on any error)
  ism-requirements-au status
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="ism-requirements-au", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("serve")
    s.add_argument("--http", action="store_true")
    s.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    s.add_argument("--root", action="append", default=[], help="directory clients may read (repeatable; required with --http)")
    rv = sub.add_parser("review")
    rv.add_argument("path", type=Path)
    rv.add_argument("--entity-type", required=True, choices=["non_corporate_commonwealth", "corporate_commonwealth", "state_territory", "private_sector", "other"])
    rv.add_argument("--classification", default="PROTECTED")
    rv.add_argument("--hosting", default="unknown", choices=["unknown", "cloud_csp", "on_premises", "hybrid", "gateway"])
    rv.add_argument("--phase", default="implement", choices=["define", "select", "implement", "assess", "authorise", "monitor"])
    rv.add_argument("--exclude", action="append", default=None)
    rv.add_argument("--json", action="store_true")
    rv.add_argument("--fail-on", default="blocker", choices=["blocker", "gap", "never"])
    vf = sub.add_parser("verify")
    vf.add_argument("path", type=Path, nargs="?", default=Path("."))
    vf.add_argument("--manifest", type=Path)
    vf.add_argument("--strict", action="store_true")
    vf.add_argument("--json", action="store_true")
    sub.add_parser("status")
    a = ap.parse_args(argv)

    if a.cmd in (None, "serve"):
        if getattr(a, "root", None):
            os.environ["ISM_REQUIREMENTS_AU_ROOTS"] = os.pathsep.join(str(Path(r).resolve()) for r in a.root)
        from .server import main as serve

        serve(http=getattr(a, "http", False), host=getattr(a, "host", "127.0.0.1"), port=getattr(a, "port", 8000))
        return
    from . import kb as _kb

    kb = _kb.load()
    if a.cmd == "status":
        from .server import kb_status

        print(json.dumps(kb_status(), indent=1))
        return
    if a.cmd == "verify":
        from . import track as _tr

        r = _tr.verify(kb, a.path, a.manifest.resolve() if a.manifest else None, a.strict)
        if a.json:
            print(json.dumps(r, indent=1))
        else:
            for e in r["errors"]:
                print(f"error: {e}")
            for w in r["warnings"]:
                print(f"warning: {w}")
            print(f"{'ok' if r['ok'] else 'FAILED'}: {r.get('controls', 0)} control entries checked against ISM {kb.release}")
        sys.exit(0 if r["ok"] else 1)
    from . import review as _rv

    full = _rv.build(kb, a.path, classification=a.classification, entity_type=a.entity_type, hosting=a.hosting, phase=a.phase, exclude=a.exclude)
    if a.json:
        print(json.dumps(_rv.compact(full, detail="full"), indent=1))
    else:
        c = _rv.compact(full, limit=10)
        by = c["summary"]["by_level"]
        print(f"ISM {kb.release} review of {full['root']} ({full['applicability']['classification']}, phase {a.phase}); run {full['run_id']}")
        print("levels:", ", ".join(f"{k}={v}" for k, v in by.items()))
        for lv, items in c["findings"].items():
            for f in items:
                print(f"[{lv.upper():7}] {f['rule']:22} {f.get('at', '(repository)')}\n    {f['title']}: {f['why']}")
        print("\nRun with --json for the full detail.")
    worst = {"blocker": ["blocker"], "gap": ["blocker", "gap"], "never": []}[a.fail_on]
    sys.exit(1 if any(full["summary"]["by_level"][lv] for lv in worst) else 0)
