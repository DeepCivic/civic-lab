"""Read the first sheet of an .xlsx with the standard library.

DFAT publishes one plain sheet, so a spreadsheet dependency would be the largest thing in the
package for the least work. This reads values only: no formulas, styles or merged cells. Dates
arrive as serial numbers, and the caller knows which columns are dates.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}
MAX_UNCOMPRESSED = 200_000_000  # a zip bomb guard; the real file is a few MB


class XlsxError(ValueError):
    pass


def _col(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref)
    if not letters:
        raise XlsxError(f"bad cell reference {ref!r}")
    n = 0
    for ch in letters.group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _text(el: ET.Element) -> str:
    return "".join(t.text or "" for t in el.iter(f"{{{_NS['m']}}}t"))


def read_first_sheet(path: Path) -> tuple[str, list[list[object]]]:
    """Return (sheet name, rows). Empty cells are None; numbers are int when whole, else float."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise XlsxError(f"not a readable .xlsx file: {exc}") from exc
    with zf:
        if sum(i.file_size for i in zf.infolist()) > MAX_UNCOMPRESSED:
            raise XlsxError("workbook expands to an implausible size; refusing to read it")
        try:
            book = ET.fromstring(zf.read("xl/workbook.xml"))
            rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            first = book.find("m:sheets/m:sheet", _NS)
            if first is None:
                raise XlsxError("workbook has no sheets")
            rid = first.get(f"{{{_NS['r']}}}id")
            target = next(r.get("Target") for r in rels.findall("pr:Relationship", _NS) if r.get("Id") == rid)
            sheet_path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
            shared: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                shared = [_text(si) for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall("m:si", _NS)]
            sheet = ET.fromstring(zf.read(sheet_path))
        except (KeyError, StopIteration, ET.ParseError) as exc:
            raise XlsxError(f"unexpected workbook structure: {exc!r}") from exc

    rows: list[list[object]] = []
    for row in sheet.findall("m:sheetData/m:row", _NS):
        cells: dict[int, object] = {}
        for c in row.findall("m:c", _NS):
            kind, v = c.get("t"), c.find("m:v", _NS)
            value: object
            if kind == "inlineStr":
                value = _text(c)
            elif v is None or v.text is None:
                continue
            elif kind == "s":
                value = shared[int(v.text)]
            elif kind == "b":
                value = v.text == "1"
            elif kind in ("str", "e"):
                value = v.text
            else:
                num = float(v.text)
                value = int(num) if num.is_integer() else num
            cells[_col(c.get("r", ""))] = value
        rows.append([cells.get(i) for i in range(max(cells) + 1)] if cells else [])
    return first.get("name", ""), rows
