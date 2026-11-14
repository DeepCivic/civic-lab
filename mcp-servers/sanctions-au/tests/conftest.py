"""Synthetic fixtures. Every name, number and record here is invented; no real list data is committed."""

from __future__ import annotations

import datetime as dt
import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

from sanctions_au import abf, dfat, store

HEADER = dfat.REQUIRED
SERIAL_2025_01_01 = 45658  # Excel day number for 2025-01-01


def _col(i: int) -> str:
    return chr(65 + i)


def make_xlsx(path: Path, rows: list[dict], sheet: str = "Consolidated List - 13_11_2026", header=HEADER) -> Path:
    """A one-sheet workbook shaped like DFAT's: shared strings, whole numbers, booleans."""
    strings: list[str] = []

    def cell(r: int, c: int, v: object) -> str:
        ref = f"{_col(c)}{r}"
        if v is None:
            return ""
        if isinstance(v, bool):
            return f'<c r="{ref}" t="b"><v>{int(v)}</v></c>'
        if isinstance(v, (int, float)):
            return f'<c r="{ref}"><v>{v}</v></c>'
        if str(v) not in strings:
            strings.append(str(v))
        return f'<c r="{ref}" t="s"><v>{strings.index(str(v))}</v></c>'

    body = [[cell(1, i, h) for i, h in enumerate(header)]]
    for n, row in enumerate(rows, start=2):
        body.append([cell(n, i, row.get(h)) for i, h in enumerate(header)])
    sheet_xml = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                 + "".join(f'<row r="{n}">{"".join(cells)}</row>' for n, cells in enumerate(body, start=1))
                 + "</sheetData></worksheet>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml",
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   f'<sheet name="{escape(sheet)}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
                   'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        z.writestr("xl/sharedStrings.xml",
                   '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   + "".join(f"<si><t>{escape(s)}</t></si>" for s in strings) + "</sst>")
    return path


def dfat_row(ref, name, kind="Individual", name_type="Primary Name", **kw) -> dict:
    base = {"Reference": ref, "Name of Individual or Entity": name, "Type": kind, "Name Type": name_type,
            "Committees": "Autonomous (Testland)", "Control Date": SERIAL_2025_01_01,
            "Instrument of Designation": "Test Sanctions Regulation 2025", "Listing Information": "Listed on 1 Jan 2025",
            "Targeted Financial Sanction": True, "Travel Ban": True, "Arms Embargo": False, "Maritime Restriction": False}
    base.update(kw)
    return base


DFAT_ROWS = [
    dfat_row(1, "Kellan DRESDORF", **{"Date of Birth": "1971, 1972", "Citizenship": "Freedonia",
                                      "Address": "14 Quarry Lane, Port Vesper, Freedonia",
                                      "Additional Information": "Passport no: Freedonia number FX1234567 (expires 2030)"}),
    dfat_row("1a", "Kel Dresdorff", name_type="Alias", **{"Alias Strength": "Strong"}),
    dfat_row("1b", "Келлан Дрездорф", name_type="Original Script"),
    dfat_row(2, "Orlov Maritime Holdings", "Entity", **{"Address": "Harbour Street, Port Vesper"}),
    dfat_row(3, "NORTHERN QUILL", "Vessel", **{"IMO Number": 9999991}),
    dfat_row(4, "Marisol Venn", **{"Date of Birth": "Approximately 1980", "Citizenship": "Ruritania"}),
]

ABF_ROWS = [
    {"sponsorname": "Quillfeather Staffing Pty Ltd", "tradingname": "QF Staffing", "abn": "11000000000", "state": "VIC",
     "postcode": "3000", "sanctionimposed": "Sponsorship cancelled and sanction bar", "sanctionimposeddate": "20200115",
     "sanctionenddate": "15-Jan-2025", "obligationbreached": "2.79, 2.82", "sanctioninfribreachnotice": "",
     "sanctioninfrinoticedate": "", "sanctioninfrinoticeamount": "", "amountstatus": ""},
    {"sponsorname": "Brackenridge Hospitality Pty Ltd*", "tradingname": "", "abn": "22000000000", "state": "nsw ",
     "postcode": "2000", "sanctionimposed": "Sanction bar", "sanctionimposeddate": "20240301",
     "sanctionenddate": "", "obligationbreached": "2.86", "sanctioninfribreachnotice": "2.86",
     "sanctioninfrinoticedate": "01-Apr-2024", "sanctioninfrinoticeamount": "$13,320",
     "amountstatus": "<img src='/x/circle-cross.png' alt='Unpaid' title='Unpaid'/>"},
    {"sponsorname": "Dresdorf, Kellan", "tradingname": "", "abn": "", "state": "QLD", "postcode": "4000",
     "sanctionimposed": "Sanction bar", "sanctionimposeddate": "", "sanctionenddate": "", "obligationbreached": "",
     "sanctioninfribreachnotice": "", "sanctioninfrinoticedate": "", "sanctioninfrinoticeamount": "", "amountstatus": ""},
    {"sponsorname": "Nine Digit Holdings Pty Ltd", "tradingname": "", "abn": "123456780", "state": "WA", "postcode": "6000",
     "sanctionimposed": "Sanction bar", "sanctionimposeddate": "20230601", "sanctionenddate": "", "obligationbreached": "2.79",
     "sanctioninfribreachnotice": "", "sanctioninfrinoticedate": "", "sanctioninfrinoticeamount": "", "amountstatus": ""},
]


def abf_payload(rows=ABF_ROWS) -> bytes:
    return json.dumps({"d": {"__type": "Internet.Domain.JsonResponse", "success": True, "data": rows, "message": None}}).encode()


@pytest.fixture
def files(tmp_path) -> tuple[Path, Path]:
    x = make_xlsx(tmp_path / "dfat.xlsx", DFAT_ROWS)
    j = tmp_path / "abf.json"
    j.write_bytes(abf_payload())
    return x, j


@pytest.fixture
def root(tmp_path, files, monkeypatch) -> Path:
    """A data directory with both datasets installed."""
    r = tmp_path / "data"
    monkeypatch.setenv("SANCTIONS_DATA_DIR", str(r))
    x, j = files
    recs, facts = dfat.parse(x)
    store.commit("dfat", x, recs, {"list_date": facts["list_date"]}, root=r)
    store.commit("abf", j, abf.parse(j.read_bytes()), {}, root=r)
    return r


NOW = dt.datetime.now(dt.timezone.utc)
