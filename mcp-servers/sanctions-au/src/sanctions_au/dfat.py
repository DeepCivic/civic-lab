"""DFAT Consolidated List: parse the published workbook into one record per listing.

The sheet has one row per name. A listing "2" has its primary name on row "2" and its aliases
and original-script names on rows "2a", "2b", and so on, each repeating the listing's details.
Parsing is strict. A column that has moved, an unknown name type or a listing with no primary
name raises DatasetError, so a changed layout stops a refresh instead of quietly producing a
dataset with holes in it.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

from .store import DatasetError
from .xlsx import XlsxError, read_first_sheet

SOURCE_URL = "https://www.dfat.gov.au/sites/default/files/Australian_Sanctions_Consolidated_List.xlsx"
PAGE_URL = "https://www.dfat.gov.au/international-relations/security/sanctions/consolidated-list"

REQUIRED = [
    "Reference", "Name of Individual or Entity", "Type", "Name Type", "Alias Strength", "Date of Birth",
    "Place of Birth", "Citizenship", "Address", "Additional Information", "Listing Information", "IMO Number",
    "Committees", "Control Date", "Instrument of Designation", "Targeted Financial Sanction", "Travel Ban",
    "Arms Embargo", "Maritime Restriction",
]
TYPES = {"Individual", "Entity", "Vessel"}
NAME_TYPES = {"Primary Name": "primary", "Alias": "alias", "Original Script": "original_script"}
_EPOCH = dt.date(1899, 12, 30)


def _s(v: object) -> str | None:
    if v is None:
        return None
    text = str(v).strip()
    return text or None


def _date(v: object) -> str | None:
    if isinstance(v, (int, float)):
        return (_EPOCH + dt.timedelta(days=int(v))).isoformat()
    return _s(v)


def _dob(v: object) -> str | None:
    """Date of birth is usually free text, but a cell typed as a date arrives as a day number. A whole
    number that is a plausible year is kept as the year; any other number is converted to a date, so
    the birth year can still be compared."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(int(v)) if float(v).is_integer() and 1800 <= v <= 2100 else _date(v)
    return _s(v)


def parse(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (records, facts about the file)."""
    try:
        sheet_name, rows = read_first_sheet(path)
    except XlsxError as exc:
        raise DatasetError(f"DFAT file: {exc}") from exc
    if not rows:
        raise DatasetError("DFAT file: the sheet is empty")
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    missing = [h for h in REQUIRED if h not in header]
    if missing:
        raise DatasetError(f"DFAT file: expected columns are missing: {', '.join(missing)}. "
                           "The published layout may have changed; no dataset was replaced.")
    col = {h: header.index(h) for h in REQUIRED}

    def cell(row: list[object], name: str) -> object:
        i = col[name]
        return row[i] if i < len(row) else None

    listings: dict[str, dict[str, Any]] = {}
    for n, row in enumerate(rows[1:], start=2):
        if not any(v is not None for v in row):
            continue
        ref = _s(cell(row, "Reference"))
        m = re.match(r"\d+", ref or "")
        if not m:
            raise DatasetError(f"DFAT file row {n}: reference {ref!r} does not start with a number")
        base, name = m.group(), _s(cell(row, "Name of Individual or Entity"))
        kind, name_type = _s(cell(row, "Type")), _s(cell(row, "Name Type"))
        if kind not in TYPES or name_type not in NAME_TYPES or not name:
            raise DatasetError(f"DFAT file row {n}: unrecognised type {kind!r}, name type {name_type!r} "
                               "or a missing name")
        rec = listings.setdefault(base, {"id": base, "type": kind, "name": None, "aliases": [], "_row": None})
        if NAME_TYPES[name_type] == "primary":
            if rec["name"] is not None:
                raise DatasetError(f"DFAT file row {n}: listing {base} has two primary names")
            rec["name"], rec["_row"] = name, row
        else:
            rec["aliases"].append({"name": name, "kind": NAME_TYPES[name_type],
                                   "strength": (_s(cell(row, "Alias Strength")) or "").lower() or None})
        if rec["_row"] is None:
            rec["_row"] = row  # details come from the primary row when there is one, see below

    out: list[dict[str, Any]] = []
    for base, rec in listings.items():
        if rec["name"] is None:
            raise DatasetError(f"DFAT file: listing {base} has no primary name row")
        row = rec.pop("_row")
        imo = _s(cell(row, "IMO Number"))
        out.append({
            **rec,
            "date_of_birth": _dob(cell(row, "Date of Birth")),
            "place_of_birth": _s(cell(row, "Place of Birth")),
            "citizenship": _s(cell(row, "Citizenship")),
            "address": _s(cell(row, "Address")),
            "additional_information": _s(cell(row, "Additional Information")),
            "listing_information": _s(cell(row, "Listing Information")),
            "imo": imo,
            "committees": _s(cell(row, "Committees")),
            "control_date": _date(cell(row, "Control Date")),
            "instrument_of_designation": _s(cell(row, "Instrument of Designation")),
            "measures": {
                "targeted_financial_sanction": cell(row, "Targeted Financial Sanction"),
                "travel_ban": cell(row, "Travel Ban"),
                "arms_embargo": cell(row, "Arms Embargo"),
                "maritime_restriction": cell(row, "Maritime Restriction"),
            },
        })
    listed = re.search(r"(\d{2})_(\d{2})_(\d{4})", sheet_name)
    return out, {
        "sheet_name": sheet_name,
        "list_date": f"{listed.group(3)}-{listed.group(2)}-{listed.group(1)}" if listed else None,
        "name_rows": len(rows) - 1,
    }
