"""SSP annex support: the schema of ASD's template, and the five user-owned columns drafted from the tracking manifest."""

from __future__ import annotations

import csv
import io
import json

from . import track as T
from .kb import KB, classification_tag

TEMPLATE = {
    "name": "System security plan annex template", "version": "September 2026",
    "url": "https://www.cyber.gov.au/sites/default/files/2026-08/System%20security%20plan%20annex%20template%20%28September%202026%29.xlsx",
    "controls_sheet_columns": ["Guideline", "Section", "Topic", "Identifier", "Revision", "Updated", "NC", "OS", "P", "S", "TS", "ML1", "ML2", "ML3",
                               "Description", "Responsibility", "Implementation Status", "Implementation Source", "Assessment Outcome", "Assessment Comments"],
    "principles_sheet_columns": ["Function", "Identifier", "Topic", "Description", "Responsibility", "Implementation Status", "Implementation Source",
                                 "Assessment Outcome", "Assessment Comments"],
    "user_owned_columns": ["Responsibility", "Implementation Status", "Implementation Source", "Assessment Outcome", "Assessment Comments"],
    "value_lists": {
        "Responsibility": T.RESPONSIBILITY,
        "Implementation Status": ["Not Determined", "Implemented", "Not Implemented", "Alternative Measures", "Not Applicable"],
        "Implementation Source": T.SOURCE,
        "Assessment Outcome": ["Not Assessed", "Fully Effective", "Partially Effective", "Not Effective", "Insufficient Evidence", "Not Applicable"],
    },
    "assessment_outcome_rule": "Assessor-set. This server only ever proposes 'Not Assessed'.",
}

STATUS_MAP = {"implemented": "Implemented", "not_applicable": "Not Applicable"}


def schema() -> dict:
    return TEMPLATE


def xlsx_instructions() -> list[str]:
    return [
        f"Download ASD's template ({TEMPLATE['version']}) from {TEMPLATE['url']}; it already holds the identifying columns (Guideline to Description).",
        "Save the draft_ssp_annex output as CSV, with the Identifier column first.",
        "In the template's Controls sheet, add a helper sheet and paste the CSV there.",
        "For each of Responsibility, Implementation Status, Implementation Source, Assessment Outcome and Assessment Comments, fill the template column with "
        "=IFERROR(VLOOKUP($D2, Helper!$A:$F, <column index>, FALSE), \"\") (D is Identifier in the template). Then paste values over the formulas so the drop-downs keep working.",
        "Check any cell that does not match its drop-down list; the template enforces the value lists in schema().",
        "Leave Assessment Outcome and Assessment Comments to the assessor; the draft proposes only 'Not Assessed'.",
    ]


def draft(kb: KB, manifest: dict, *, applicable_only: bool = True, sections: list[str] | None = None, fmt: str = "csv", include_comments: bool = True,
          sheet: str = "controls") -> dict:
    if fmt not in ("csv", "json"):
        raise ValueError("format must be csv or json")
    if sheet not in ("controls", "principles"):
        raise ValueError("sheet must be controls or principles")
    scope = manifest.get("scope") or {}
    tag = classification_tag(str(scope.get("classification", ""))) if scope.get("classification") else None
    e8t = scope.get("e8_target") if scope.get("e8_target") in ("ML1", "ML2", "ML3") else None
    have = {str(c.get("id", "")).upper(): c for c in manifest.get("controls", [])}
    rows = []
    for c in kb.controls("principle" if sheet == "principles" else "control"):
        if sheet == "controls":
            if applicable_only and tag and not kb.applies(c, tag, e8t):
                continue
            if sections and not any(s.lower() in c["section"].lower() or s.lower() in c["guideline"].lower() or s.lower() in c["topic"].lower() for s in sections):
                continue
        m = have.get(c["id"])
        if m:
            status = STATUS_MAP.get(m.get("status"), "Not Determined")
            comment = ""
            if m.get("status") in ("partial", "planned", "risk_accepted"):
                comment = f"Tracking status: {m['status']}." + (f" {m['note']}" if m.get("note") else "")
            elif m.get("note"):
                comment = str(m["note"])
            rows.append({"Identifier": c["id"], "Responsibility": m.get("responsibility", "Not Determined"), "Implementation Status": status,
                         "Implementation Source": m.get("source", "Not Determined"), "Assessment Outcome": "Not Assessed", "Assessment Comments": comment})
        else:
            rows.append({"Identifier": c["id"], "Responsibility": "Not Determined", "Implementation Status": "Not Determined",
                         "Implementation Source": "Not Determined", "Assessment Outcome": "Not Assessed", "Assessment Comments": ""})
    cols = ["Identifier"] + TEMPLATE["user_owned_columns"]
    if not include_comments:
        cols.remove("Assessment Comments")
        for r in rows:
            r.pop("Assessment Comments", None)
    pointer = (f"Identifying columns (Guideline to Description) come from ASD's template ({TEMPLATE['version']}): {TEMPLATE['url']}. "
               "Merge by Identifier; ssp_annex_xlsx_instructions has the steps.")
    out = {"rows": len(rows), "tracked": sum(1 for r in rows if r["Identifier"] in have), "sheet": sheet, "template": pointer}
    if fmt == "csv":
        buf = io.StringIO()
        wr = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)
        out["csv"] = buf.getvalue()
    else:
        out["columns"] = cols
        out["json"] = json.dumps(rows, separators=(",", ":"))
    out["rule"] = "Statuses come only from the manifest. partial, planned, risk_accepted and untracked controls are 'Not Determined'; Assessment Outcome is always 'Not Assessed'."
    return out
